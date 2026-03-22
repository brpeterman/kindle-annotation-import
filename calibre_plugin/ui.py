from calibre.gui2.actions import InterfaceAction


class KindleAnnotationImportAction(InterfaceAction):
    name = "Kindle Annotation Import"
    action_spec = (
        "Import Kindle Annotations",
        None,
        "Import highlights and notes from Kindle My Clippings.txt or a Notebook HTML file",
        None,
    )

    def genesis(self):
        self.qaction.triggered.connect(self.show_dialog)

    def show_dialog(self):
        from calibre_plugins.kindle_annotation_import.main import ImportDialog

        d = ImportDialog(self.gui)
        d.exec()
