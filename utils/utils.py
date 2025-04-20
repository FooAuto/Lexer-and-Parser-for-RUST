# import matplotlib.pyplot as plt
import sys
import os
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QGraphicsScene, QGraphicsView,
    QGraphicsObject, QAction, QFileDialog
)
from PyQt5.QtGui import (
    QBrush, QColor, QPainter, QPen, QFont, QFontMetrics, QPainterPath,
    QIcon, QLinearGradient
)
from PyQt5.QtCore import (
    QRectF, Qt, QPointF, QPropertyAnimation, QObject, pyqtSignal
)
import sys

# def visualize_tree_pyqt(node):
#     class TreeVisualizer(QMainWindow):  # 改为继承自QMainWindow
#         def __init__(self, root_node):
#             super().__init__()

#             # 创建场景和视图
#             self.scene = QGraphicsScene()
#             self.view = QGraphicsView(self.scene)
#             self.view.setRenderHint(QPainter.Antialiasing)
#             self.setCentralWidget(self.view)  # 将视图设置为中心部件

#             self.setWindowTitle("Tree Visualization")
            
#             # 布局参数
#             self.node_padding = 10
#             self.h_spacing = 120
#             self.v_spacing = 100
#             self.positions = {}
#             self.counter = {"x": 0}

#             # 缩放参数
#             self.scale_factor = 1.0
#             self.zoom_factor = 1.1

#             # 创建工具栏
#             self.toolbar = self.addToolBar("MainToolbar")  # 使用QMainWindow的addToolBar
#             self.add_toolbar_actions()

#             # 绘制树
#             self.draw_tree(root_node)
#             self.view.setSceneRect(self.scene.itemsBoundingRect())
#             self.setMinimumSize(800, 600)

#         def add_toolbar_actions(self):
#             # 缩放入
#             zoom_in_action = QAction(QIcon(), "Zoom In", self)
#             zoom_in_action.triggered.connect(self.zoom_in)
#             self.toolbar.addAction(zoom_in_action)

#             # 缩放出
#             zoom_out_action = QAction(QIcon(), "Zoom Out", self)
#             zoom_out_action.triggered.connect(self.zoom_out)
#             self.toolbar.addAction(zoom_out_action)

#             # 导出
#             export_action = QAction(QIcon(), "Export", self)
#             export_action.triggered.connect(self.export_image)
#             self.toolbar.addAction(export_action)

#         # 以下方法保持原有实现不变（略作调整视图访问方式）
#         def draw_tree(self, node):
#             self.traverse_and_place(node)
#             for nid, (x, y, data) in self.positions.items():
#                 self.draw_node(x, y, data["root"])
#                 parent_id = data.get("parent_id")
#                 if parent_id:
#                     px, py, _ = self.positions[parent_id]
#                     self.draw_edge(px, py, x, y)

#         def traverse_and_place(self, node, depth=0, parent_id=None):
#             nid = id(node)
#             x = self.counter["x"] * self.h_spacing
#             y = depth * self.v_spacing
#             self.positions[nid] = (x, y, {"root": node["root"], "parent_id": parent_id})
#             self.counter["x"] += 1
#             for child in node.get("children", []):
#                 self.traverse_and_place(child, depth + 1, nid)

#         def draw_node(self, x, y, text):
#             text_item = QGraphicsTextItem(text)
#             text_item.setFont(QFont("Consolas", 10, QFont.Bold))
#             text_rect = text_item.boundingRect()
#             rect_width = text_rect.width() + self.node_padding * 2 
#             rect_height = text_rect.height() + self.node_padding * 2

#             rect = QGraphicsRectItem(
#                 x - rect_width / 2,
#                 y - rect_height / 2,
#                 rect_width,
#                 rect_height
#             )
#             rect.setBrush(QBrush(QColor("#6BBF6A")))
#             rect.setPen(QPen(QColor("#4C4C4C"), 2))
#             self.scene.addItem(rect)

#             text_item.setPos(x - text_rect.width() / 2, y - text_rect.height() / 2)
#             text_item.setDefaultTextColor(QColor(255, 255, 255))
#             self.scene.addItem(text_item)

#         def draw_edge(self, x1, y1, x2, y2):
#             path = QPainterPath()
#             path.moveTo(x1, y1 + self.node_padding * 2 + 1)
#             path.lineTo(x1, y1 + self.node_padding * 2 + 1 + 20)
#             path.lineTo(x2, y1 + self.node_padding * 2 + 20)
#             path.lineTo(x2, y2 - self.node_padding * 2 - 1)
#             self.scene.addPath(path, QPen(QColor(0, 0, 0), 2))

#         def zoom_in(self):
#             self.view.scale(self.zoom_factor, self.zoom_factor)
#             self.scale_factor *= self.zoom_factor

#         def zoom_out(self):
#             self.view.scale(1/self.zoom_factor, 1/self.zoom_factor)
#             self.scale_factor /= self.zoom_factor

#         def export_image(self):
#             file_path, _ = QFileDialog.getSaveFileName(
#                 self, "Save Image", "", "PNG Image (*.png)")
#             if file_path:
#                 pixmap = self.view.grab()
#                 pixmap.save(file_path, "PNG")

#         def wheelEvent(self, event):
#             # 将滚轮事件传递给视图
#             self.view.wheelEvent(event)

#     # 运行应用
#     app = QApplication.instance() or QApplication(sys.argv)
#     viewer = TreeVisualizer(node)
#     viewer.show()
#     app.exec_()

def visualize_tree_pyqt(node):
    class SignalEmitter(QObject):
        hover_entered = pyqtSignal(str)
        hover_left = pyqtSignal(str)

    class NodeRectItem(QGraphicsObject):
        def __init__(self, nid, x, y, w, h, text):
            super().__init__()
            self.nid = nid
            self.rect = QRectF(-w / 2, -h / 2, w, h)
            self.text = text
            self.signal = SignalEmitter()
            self.setAcceptHoverEvents(True)
            # Colors set externally for theme
            self.colors = ()
            self.hover_colors = ()
            self.text_color = QColor(255, 255, 255)
            self.border_color = QColor(255, 255, 255)
            self.font = QFont("Arial", 10, QFont.Bold)

        def boundingRect(self):
            return self.rect

        def paint(self, painter, option, widget):
            grad = QLinearGradient(self.rect.topLeft(), self.rect.bottomRight())
            grad.setColorAt(0, self.colors[0])
            grad.setColorAt(1, self.colors[1])
            painter.setBrush(QBrush(grad))
            painter.setPen(QPen(self.border_color, 2))
            painter.drawRoundedRect(self.rect, 10, 10)
            painter.setFont(self.font)
            painter.setPen(self.text_color)
            painter.drawText(self.rect, Qt.AlignCenter, self.text)

        def hoverEnterEvent(self, event):
            self.signal.hover_entered.emit(self.nid)
            self.setCursor(Qt.PointingHandCursor)
            super().hoverEnterEvent(event)

        def hoverLeaveEvent(self, event):
            self.signal.hover_left.emit(self.nid)
            self.setCursor(Qt.ArrowCursor)
            super().hoverLeaveEvent(event)

    class TreeVisualizer(QMainWindow):
        def __init__(self, root_node):
            super().__init__()
            os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
            self.node_items = {}
            self.node_children = {}
            self.animations = {}
            self.is_day = False  # start in night mode

            # Scene and view
            self.scene = QGraphicsScene()
            self.view = QGraphicsView(self.scene)
            self.view.setRenderHint(QPainter.Antialiasing)
            self.setCentralWidget(self.view)
            self.setup_themes()
            self.apply_theme()

            self.setWindowTitle("Stylish Tree Visualization")
            self.node_padding = 10
            self.h_spacing = 140
            self.v_spacing = 120
            self.positions = {}
            self.counter = {"x": 0}
            self.zoom_factor = 1.1

            self.toolbar = self.addToolBar("MainToolbar")
            self.add_toolbar_actions()

            self.draw_tree(root_node)
            self.view.setSceneRect(self.scene.itemsBoundingRect())
            self.setMinimumSize(900, 700)

        def setup_themes(self):
            # Night theme
            self.night_bg = (QColor("#282C34"), QColor("#484F58"))
            self.night_node = ((QColor("#61AFEF"), QColor("#528BFF")),
                            (QColor("#C678DD"), QColor("#A566CC")))
            # Day theme
            self.day_bg = (QColor("#FFFFFF"), QColor("#E0E0E0"))
            self.day_node = ((QColor("#AED6F1"), QColor("#85C1E9")),
                            (QColor("#F4D03F"), QColor("#F1C40F")))

        def apply_theme(self):
            # Background
            top, bottom = (self.day_bg if self.is_day else self.night_bg)
            bg_grad = QLinearGradient(0, 0, 0, self.height())
            bg_grad.setColorAt(0, top)
            bg_grad.setColorAt(1, bottom)
            self.scene.setBackgroundBrush(QBrush(bg_grad))
            # Nodes
            defaults, hovers = (self.day_node if self.is_day else self.night_node)
            for info in self.node_items.values():
                node = info['rect']
                node.colors = defaults
                node.hover_colors = hovers
                node.update()

        def add_toolbar_actions(self):
            zoom_in = QAction(QIcon(), "Zoom In", self)
            zoom_in.triggered.connect(lambda: self.view.scale(self.zoom_factor, self.zoom_factor))
            self.toolbar.addAction(zoom_in)
            zoom_out = QAction(QIcon(), "Zoom Out", self)
            zoom_out.triggered.connect(lambda: self.view.scale(1/self.zoom_factor, 1/self.zoom_factor))
            self.toolbar.addAction(zoom_out)
            export = QAction(QIcon(), "Export", self)
            export.triggered.connect(self.export_image)
            self.toolbar.addAction(export)
            # Day/Night toggle
            toggle = QAction("Day Mode", self)
            toggle.setCheckable(True)
            toggle.triggered.connect(self.toggle_mode)
            self.toolbar.addAction(toggle)

        def toggle_mode(self, checked):
            self.is_day = checked
            # Update button text
            button = self.sender()
            button.setText("Night Mode" if self.is_day else "Day Mode")
            self.apply_theme()

        def draw_tree(self, node):
            self.traverse_and_place(node, path="root")

        def traverse_and_place(self, node, depth=0, parent_id=None, path="root"):
            nid = path
            x = self.counter["x"] * self.h_spacing
            y = depth * self.v_spacing
            self.positions[nid] = (x, y, {"label": node["root"], "parent_id": parent_id})
            self.counter["x"] += 1
            for idx, child in enumerate(node.get("children", [])):
                child_path = f"{path}.{idx}"
                self.traverse_and_place(child, depth + 1, nid, child_path)
            if parent_id:
                self.node_children.setdefault(parent_id, []).append(nid)
                px, py, _ = self.positions[parent_id]
                self.draw_edge(px, py, x, y)
            self.draw_node(x, y, node["root"], nid)

        def draw_node(self, x, y, text, nid):
            fm = QFontMetrics(QFont("Arial", 10, QFont.Bold))
            text_rect = fm.boundingRect(text)
            w, h = text_rect.width()+self.node_padding*2, text_rect.height()+self.node_padding*2
            node_item = NodeRectItem(nid, x, y, w, h, text)
            node_item.setPos(QPointF(x, y))
            node_item.signal.hover_entered.connect(self.handle_hover_enter)
            node_item.signal.hover_left.connect(self.handle_hover_leave)
            # initialize theme colors
            defaults, hovers = (self.day_node if self.is_day else self.night_node)
            node_item.colors, node_item.hover_colors = defaults, hovers
            self.scene.addItem(node_item)
            self.node_items[nid] = {'rect': node_item, 'original_pos': QPointF(x, y)}

        def draw_edge(self, px, py, cx, cy):
            path = QPainterPath()
            start = QPointF(px, py + self.node_padding)
            end = QPointF(cx, cy - self.node_padding)
            mid = QPointF((start.x()+end.x())/2, (start.y()+end.y())/2)
            path.moveTo(start)
            ctrl = QPointF(mid.x(), start.y() - 30)
            path.quadTo(ctrl, end)
            pen = QPen(QColor("#ABB2BF"), 2)
            pen.setCapStyle(Qt.RoundCap)
            self.scene.addPath(path, pen)

        def handle_hover_enter(self, nid):
            for child in self.get_all_children(nid)+[nid]:
                item = self.node_items[child]
                anim = QPropertyAnimation(item['rect'], b"pos")
                anim.setDuration(200)
                anim.setStartValue(item['rect'].pos())
                anim.setEndValue(item['original_pos']+QPointF(0,-20))
                anim.start()
                self.animations[child] = anim
                item['rect'].colors = item['rect'].hover_colors
                item['rect'].update()

        def handle_hover_leave(self, nid):
            for child in self.get_all_children(nid)+[nid]:
                item = self.node_items[child]
                anim = QPropertyAnimation(item['rect'], b"pos")
                anim.setDuration(200)
                anim.setStartValue(item['rect'].pos())
                anim.setEndValue(item['original_pos'])
                anim.start()
                self.animations[child] = anim
                defaults = (self.day_node if self.is_day else self.night_node)[0]
                item['rect'].colors = defaults
                item['rect'].update()

        def get_all_children(self, nid):
            res, stack = [], [nid]
            while stack:
                cur = stack.pop()
                for c in self.node_children.get(cur, []):
                    res.append(c); stack.append(c)
            return res

        def export_image(self):
            file_path, _ = QFileDialog.getSaveFileName(self, "Save Image", "", "PNG Image (*.png)")
            if file_path:
                self.view.grab().save(file_path, "PNG")

        def wheelEvent(self, event):
            self.view.wheelEvent(event)

    # 运行应用
    app = QApplication.instance() or QApplication(sys.argv)
    viewer = TreeVisualizer(node)
    viewer.show()
    app.exec_()


def serialize_token(token):
    return {
        key: (value.name if hasattr(value, "name") else value)
        for key, value in token.items()
    }


def print_tree(node, indent=0):
    print("  " * indent + str(node["root"]))
    for child in node.get("children", []):
        print_tree(child, indent + 1)


# def visualize_tree_matplotlib(node):
#     fig, ax = plt.subplots()
#     ax.axis("off")

#     positions = {}  # 节点 id -> (x,y)
#     nodes = {}  # 节点 id -> node dict
#     edges = []  # list of (parent_id, child_id)
#     counter = {"x": 0}

#     def traverse(n, depth=0):
#         nid = id(n)
#         x = counter["x"]
#         y = -depth
#         positions[nid] = (x, y)
#         nodes[nid] = n
#         counter["x"] += 1
#         for child in n.get("children", []):
#             edges.append((nid, id(child)))
#             traverse(child, depth + 1)

#     traverse(node)

#     for pid, cid in edges:
#         x1, y1 = positions[pid]
#         x2, y2 = positions[cid]
#         ax.plot([x1, x2], [y1, y2], linewidth=1)

#     for nid, (x, y) in positions.items():
#         ax.text(
#             x,
#             y,
#             nodes[nid]["root"],
#             ha="center",
#             va="center",
#             bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", lw=0.8),
#         )

#     plt.tight_layout()
#     plt.show()
