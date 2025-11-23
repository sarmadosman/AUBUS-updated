# gui/rating_dialog.py

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QPushButton,
)
from PyQt5.QtCore import Qt


class RatingDialog(QDialog):
    """
    1–5 star rating dialog with optional comment.

    Usage:

        dlg = RatingDialog(self, who_label="driver Alice")
        if dlg.exec_() == QDialog.Accepted:
            score = dlg.rating   # int 1..5
            comment = dlg.comment
    """

    def __init__(self, parent=None, who_label: str = "the other user"):
        super().__init__(parent)
        self.setWindowTitle("Rate your ride")

        self.rating = 5
        self.comment = ""
        self._who_label = who_label
        self._star_buttons = []

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("How was this ride?")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        info = QLabel(
            f"Please tap a star rating for {self._who_label} (1–5)."
        )
        info.setAlignment(Qt.AlignCenter)
        info.setWordWrap(True)
        layout.addWidget(info)

        # Star buttons
        stars_row = QHBoxLayout()
        stars_row.addWidget(QLabel("Rating:"))

        self.stars_label = QLabel("5 / 5")
        self.stars_label.setAlignment(Qt.AlignRight)

        for i in range(1, 6):
            btn = QPushButton("★")
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setStyleSheet(
                "font-size: 22px; border: none; padding: 2px 4px;"
            )
            btn.clicked.connect(lambda checked, v=i: self._on_star_clicked(v))
            self._star_buttons.append(btn)
            stars_row.addWidget(btn)

        stars_row.addWidget(self.stars_label)
        layout.addLayout(stars_row)

        self._update_star_display()

        # Comment
        comment_label = QLabel("Optional comment:")
        layout.addWidget(comment_label)

        self.comment_edit = QTextEdit()
        self.comment_edit.setPlaceholderText(
            "Anything you'd like to share about this ride."
        )
        layout.addWidget(self.comment_edit)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        ok_btn = QPushButton("Submit")
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("Skip")
        cancel_btn.clicked.connect(self.reject)

        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    # -------- internal helpers --------

    def _on_star_clicked(self, value: int):
        self.rating = max(1, min(5, value))
        self._update_star_display()

    def _update_star_display(self):
        for idx, btn in enumerate(self._star_buttons, start=1):
            if idx <= self.rating:
                btn.setText("★")
            else:
                btn.setText("☆")
        self.stars_label.setText(f"{self.rating} / 5")

    def _on_ok(self):
        self.comment = self.comment_edit.toPlainText().strip()
        self.accept()
