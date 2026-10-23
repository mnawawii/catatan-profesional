import os
import sys
from pathlib import Path


def main():
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("Catatan Cornell")
    app.setOrganizationName("mnawawii")
    app.setStyle("Fusion")
    here = Path(__file__).parent
    icon = here / "icons" / "id.mnawawii.cornell.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    app.setDesktopFileName("id.mnawawii.cornell")

    # satu jendela saja
    name = f"cornell-app-{os.getuid()}"
    probe = QLocalSocket()
    probe.connectToServer(name)
    if probe.waitForConnected(300):
        probe.write(b"raise")
        probe.flush()
        probe.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.listen(name)

    from app import MainWindow
    from store import NoteStore
    store = NoteStore()
    win = MainWindow(store)
    win.show()

    def bring_front():
        conn = server.nextPendingConnection()
        if conn:
            conn.disconnectFromServer()
        win.showNormal()
        win.raise_()
        win.activateWindow()

    server.newConnection.connect(bring_front)
    QTimer.singleShot(3000, lambda: (store.backup(), win.update_backup_label()))   # cadangan mingguan, bila perlu
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
