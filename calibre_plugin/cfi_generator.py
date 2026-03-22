"""Generate EPUB CFI (Canonical Fragment Identifiers) from DOM position.

A CFI path like '/4/2/56/1:591' encodes a precise position within an XHTML document:
  - Even step numbers (2, 4, 56) refer to element children (1-based, counting only elements)
  - Odd step numbers (1, 3, 5) refer to text-node positions between/around elements
  - ':591' is the character offset within the addressed text node(s)
  - '[id]' after a step is an ID assertion for robustness

The spine prefix (e.g., '/6' for spine_index=2) is NOT included in the generated path,
since Calibre stores spine_index separately in annotations.
"""

from lxml import etree


_NS_XHTML = "http://www.w3.org/1999/xhtml"


def generate_cfi(xhtml_bytes: bytes, text_offset: int) -> str | None:
    """Generate a CFI path for a character offset in the plain text of an XHTML file.

    The text_offset refers to the position within the text extracted by the same
    iterwalk approach used in epub_reader._extract_text_with_anchors.

    Returns a CFI path string (e.g., '/4/2/56/1:591') or None if the offset
    is out of range.
    """
    tree = etree.fromstring(xhtml_bytes)

    # Phase 1: Walk the DOM to find which text segment contains our offset.
    # We need to identify: the element the text belongs to, whether it's .text
    # or .tail, and the character offset within that specific text segment.
    target = _find_text_location(tree, text_offset)
    if target is None:
        return None

    target_element, is_tail, local_offset = target

    # Phase 2: Build the CFI path from root down to the target.
    return _build_cfi_path(tree, target_element, is_tail, local_offset)


def _find_text_location(tree, text_offset):
    """Walk the DOM via iterwalk to find the element and text segment at text_offset.

    Returns (element, is_tail, local_offset) or None.
    - element: the lxml element whose .text or .tail contains the target
    - is_tail: False if in element.text, True if in element.tail
    - local_offset: character position within that text segment
    """
    current_offset = 0

    for event, element in etree.iterwalk(tree, events=("start", "end")):
        if event == "start":
            if element.text:
                seg_len = len(element.text)
                if current_offset + seg_len > text_offset:
                    return (element, False, text_offset - current_offset)
                current_offset += seg_len
        elif event == "end":
            if element.tail:
                seg_len = len(element.tail)
                if current_offset + seg_len > text_offset:
                    return (element, True, text_offset - current_offset)
                current_offset += seg_len

    # Offset is exactly at the end of all text
    return None


def _build_cfi_path(tree, target_element, is_tail, local_offset):
    """Build the CFI path string from root to the target text position."""

    # Determine the reference element and text-node position:
    # - If target is in element.text: the text node is a child of that element
    #   (the first text-node child, before any child elements)
    # - If target is in element.tail: the text node is a sibling of that element,
    #   specifically the text node that follows element in parent's child list
    if is_tail:
        # The tail text of an element is the text between this element's end tag
        # and the next sibling element (or parent's end tag). In CFI terms, it's
        # a text-node child of the PARENT, positioned after this element.
        ref_parent = target_element.getparent()
        after_element = target_element
    else:
        # The .text of an element is the text before its first child element.
        # In CFI terms, it's a text-node child of this element at position /1
        # (the first child slot, which is a text node before any element children).
        ref_parent = target_element
        after_element = None

    # Build the path from root to ref_parent
    path_steps = _path_from_root(tree, ref_parent)
    if path_steps is None:
        return None

    # Compute the text-node step index within ref_parent
    text_step, accumulated_offset = _compute_text_step(ref_parent, after_element)

    # The final character offset includes any text from preceding text nodes
    # that share the same text-node slot (adjacent text nodes are merged in CFI)
    final_offset = accumulated_offset + local_offset

    # Assemble the CFI string
    cfi = ""
    for step_num, element_id in path_steps:
        cfi += f"/{step_num}"
        if element_id:
            cfi += f"[{_escape_cfi(element_id)}]"

    cfi += f"/{text_step}:{final_offset}"

    return cfi


def _path_from_root(tree, target):
    """Build the list of CFI steps from the document root to the target element.

    Returns a list of (step_number, element_id_or_None) tuples, or None if
    the target is not found.
    """
    # Build ancestry chain: [root, ..., grandparent, parent, target]
    ancestry = []
    node = target
    while node is not None:
        ancestry.append(node)
        node = node.getparent()
    ancestry.reverse()

    # The root of the lxml tree is the top element (e.g., <html>).
    # In CFI, the document root is an implicit node, and <html> is its
    # first element child at step /2 (since /1 would be a text node).
    # We start our path with /2 for the root element.
    if len(ancestry) < 1:
        return None

    steps = []
    # Step for the root element itself (<html>): always /2 in a well-formed XHTML doc
    root_id = ancestry[0].get("id")
    steps.append((2, root_id if _is_unique_id(tree, root_id) else None))

    # Steps for each descendant in the ancestry chain
    for i in range(1, len(ancestry)):
        parent = ancestry[i - 1]
        child = ancestry[i]
        step_num = _child_cfi_index(parent, child)
        child_id = child.get("id")
        steps.append((step_num, child_id if _is_unique_id(tree, child_id) else None))

    return steps


def _child_cfi_index(parent, target_child):
    """Compute the CFI child index of target_child within parent.

    Element children get even indices (2, 4, 6, ...); the implicit text-node
    slots between them get odd indices (1, 3, 5, ...).
    """
    index = 0
    for child in parent:
        index |= 1  # If even, make odd (accounts for text-node slot)
        index += 1  # Then +1 for the element (makes it even)
        if child is target_child:
            return index

    # Should not reach here if target_child is actually a child of parent
    return 0


def _compute_text_step(parent, after_element):
    """Compute the CFI text-node step index and accumulated text offset.

    - If after_element is None: we want the text before any child elements
      (the first text-node slot, index 1). Accumulated offset is 0.
    - If after_element is an element: we want the text node after that element
      (an odd index after after_element's even index). We also accumulate
      text lengths from any preceding text siblings that share this slot.
    """
    if after_element is None:
        # Text is in parent.text (before first child element) → step /1
        return 1, 0

    # Find the CFI index of after_element, then add 1 to get the text-node index
    element_index = _child_cfi_index(parent, after_element)
    text_step = element_index + 1  # Next slot after the element (odd = text)

    return text_step, 0


def _is_unique_id(tree, element_id):
    """Check if an element ID is non-empty and unique in the document."""
    if not element_id:
        return False
    try:
        matches = tree.xpath(f'//*[@id="{element_id}"]')
        return len(matches) == 1
    except Exception:
        return False


def _escape_cfi(text):
    """Escape special CFI characters with ^ prefix."""
    result = []
    for ch in text:
        if ch in "[](),;=^":
            result.append("^")
        result.append(ch)
    return "".join(result)
