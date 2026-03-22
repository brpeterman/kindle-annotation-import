from calibre.customize import InterfaceActionBase


class KindleAnnotationImportPlugin(InterfaceActionBase):
    name = "Kindle Annotation Import"
    description = "Import Kindle highlights and notes into Calibre annotations"
    supported_platforms = ["windows", "osx", "linux"]
    author = "Brandon Peterman"
    version = (0, 1, 0)
    minimum_calibre_version = (7, 0, 0)

    actual_plugin = (
        "calibre_plugins.kindle_annotation_import.ui:KindleAnnotationImportAction"
    )
