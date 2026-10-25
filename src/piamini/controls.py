"""Native Mini controls: dragging, hover cooldown and a focus-safe HTML composer."""
import time
from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QApplication


class HoverBlink:
    def __init__(self):
        self.inside = False
        self.last = -5.0

    def update(self, inside, now):
        should = inside and not self.inside and now - self.last >= 5
        self.inside = inside
        if should:
            self.last = now
        return should


class DragHandle(QLabel):
    def __init__(self, controls):
        super().__init__('⠿')
        self.controls = controls
        self.setToolTip('Segure e arraste para mover a Mini PIA')
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setFixedWidth(28)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.start = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start = event.globalPosition().toPoint()
            self.original = self.controls.overlay.pos()
            self.controls.dragging = True
            self.grabMouse()

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.controls.move_to(self.original + event.globalPosition().toPoint() - self.start)

    def mouseReleaseEvent(self, event):
        if self.start is not None:
            self.start = None
            self.controls.dragging = False
            self.releaseMouse()
            point = self.controls.overlay.pos()
            self.controls.ui.service.store.set('mini:position', [point.x(), point.y()])


class MiniControls:
    def __init__(self, ui):
        self.ui, self.overlay = ui, ui.overlay
        self.dragging = False
        self.blink = HoverBlink()
        self.menu = QWidget(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.menu.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.menu.setStyleSheet('QWidget{background:#241e31;color:#e0cff7;border-radius:10px;}QPushButton{background:#30263f;border:0;padding:9px;border-radius:7px;}QPushButton:hover{background:#4c3861;}')
        row = QHBoxLayout(self.menu)
        row.setContentsMargins(5, 5, 8, 5)
        self.handle = DragHandle(self)
        row.addWidget(self.handle)
        for name, fn in [('Mensagem', ui.open_composer), ('Microfone', ui.microphone),
                         ('Expandir', lambda: ui.set_main_visible(True)), ('Ocultar', lambda: ui.set_mini_visible(False))]:
            button = QPushButton(name)
            button.clicked.connect(fn)
            row.addWidget(button)
        self.menu.adjustSize()
        saved = ui.service.store.get('mini:position')
        if saved:
            self.move_to(QPoint(*saved))
        self.timer = QTimer(self.menu)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)
        self.top_timer = QTimer(self.menu)
        self.top_timer.timeout.connect(self.keep_on_top)
        self.top_timer.start(900)

    def nearby(self, size):
        rect = self.overlay.frameGeometry()
        screen = self.overlay.screen().availableGeometry()
        x = max(screen.left(), min(rect.right() - size.width(), screen.right() - size.width()))
        y = rect.top() - size.height() - 6
        if y < screen.top():
            y = min(rect.bottom() + 6, screen.bottom() - size.height())
        return QPoint(x, y)

    def move_to(self, point):
        screen = QApplication.screenAt(point) or self.overlay.screen()
        rect = screen.availableGeometry()
        self.overlay.move(max(rect.left(), min(point.x(), rect.right() - self.overlay.width())),
                          max(rect.top(), min(point.y(), rect.bottom() - self.overlay.height())))
        self.menu.move(self.nearby(self.menu.size()))
        if hasattr(self.ui, 'composer') and self.ui.composer.isVisible():
            self.ui.composer.move(self.nearby(self.ui.composer.size()))

    def tick(self):
        if not self.overlay.isVisible():
            self.menu.hide()
            self.blink.update(False, time.monotonic())
            return
        cursor = QCursor.pos()
        inside = self.overlay.frameGeometry().contains(cursor)
        if self.blink.update(inside, time.monotonic()):
            self.overlay.blink()
        if self.dragging or self.ui.composer.isVisible():
            return
        active = self.overlay.frameGeometry().adjusted(-12, -65, 12, 12).contains(cursor)
        if self.menu.isVisible():
            active = active or self.menu.frameGeometry().adjusted(-12, -12, 12, 12).contains(cursor)
        if active:
            self.menu.move(self.nearby(self.menu.size()))
            self.menu.show()
        else:
            self.menu.hide()

    def keep_on_top(self):
        if not self.overlay.isVisible():
            return
        self.overlay.raise_()
        import sys
        if sys.platform == 'win32':
            import ctypes
            # No activation: typing in the application behind the Mini remains unaffected.
            ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(int(self.overlay.winId())), ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)
