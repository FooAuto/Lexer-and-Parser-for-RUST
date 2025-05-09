import sys
import os
import json
from lexer.lexer import Lexer
from lexparser.lexparser import Parser
from utils.utils import *
from PyQt5.QtCore import Qt, QStandardPaths
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QFileDialog, QPushButton
from PyQt5.QtGui import QPalette, QColor


class FileDropWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rust Lexer and Parser")
        self.setGeometry(300, 300, 500, 300)

        # 设置背景色
        self.setAutoFillBackground(True)
        p = self.palette()
        p.setColor(QPalette.Background, QColor(242, 242, 242))  # 浅灰色背景
        self.setPalette(p)

        # 创建标签
        self.label = QLabel("Drag and Drop a Rust File Here", self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: #4a4a4a;
            background-color: #f4f4f4;
            padding: 30px;
            border: 2px dashed #5a5a5a;
        """)
        
        # 创建按钮
        self.button = QPushButton("Choose File", self)
        self.button.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                padding: 10px;
                background-color: #007BFF;
                color: white;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        self.button.clicked.connect(self.open_file_dialog)

        # 创建布局
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.button)

        # 设置为主窗口的布局
        self.setLayout(self.layout)

        # 启用拖放
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            # 拖动文件时改变标签颜色
            self.label.setStyleSheet("""
                font-size: 20px;
                font-weight: bold;
                color: #fff;
                background-color: #5bc0de;
                padding: 30px;
                border: 2px dashed #5a5a5a;
            """)

    def dropEvent(self, event):
        file_path = event.mimeData().urls()[0].toLocalFile()
        self.start_analysis(file_path)
        # 恢复默认标签样式
        self.label.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: #4a4a4a;
            background-color: #f4f4f4;
            padding: 30px;
            border: 2px dashed #5a5a5a;
        """)

    def open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Rust Source File", "", "Rust Files (*.rs)")
        if file_path:
            self.start_analysis(file_path)

    def start_analysis(self, file_path):
        self.label.setText("Analyzing... Please Wait.")
        self.label.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: #fff;
            background-color: #5bc0de;
            padding: 30px;
            border: 2px dashed #5a5a5a;
        """)
        QApplication.processEvents()  # 强制更新界面

        # 获取平台相关的缓存目录
        cache_dir = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
        if not cache_dir:
            cache_dir = os.getcwd()  # 如果无法获取缓存目录，使用当前工作目录

        # 创建缓存目录中的outputs文件夹
        output_dir = os.path.join(cache_dir, "outputs")
        os.makedirs(output_dir, exist_ok=True)

        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        lexer = Lexer()
        parser = Parser()
        tokens, success = lexer.getLex(lines)
        with open(os.path.join(output_dir, "result.json"), "w", encoding="utf-8") as out_file:
            json.dump(
                [serialize_token(token) for token in tokens],
                out_file,
                indent=2,
                ensure_ascii=False,
            )
        print("Tokens written to outputs/result.json")

        if success:
            print("\nLexing completed successfully.")
            print("\nNow Parser starts...")
            result = parser.parse(tokens)
            if isinstance(result, dict) and result.get("error"):
                print(f"语法错误：{result['error']}，位置：{result.get('loc')}")
                self.label.setText(f"Error: {result['error']}")
            else:
                print("\n===== 语法树 (ASCII) =====")
                print_tree(result)
                visualize_tree_pyqt(result)
                self.label.setText("Analysis Complete!")
        else:
            print("\nLexing failed: unknown tokens found.")
            self.label.setText("Lexing failed. Unknown tokens found.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FileDropWindow()
    window.show()
    sys.exit(app.exec_())
