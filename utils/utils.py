# import matplotlib.pyplot as plt
import sys
from PyQt5.QtWidgets import (
    QApplication,
    QGraphicsScene,
    QGraphicsView,
    QGraphicsEllipseItem,
    QGraphicsTextItem,
)

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QBrush, QPen, QColor, QLinearGradient, QFont, QPainterPath
from PyQt5.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QGraphicsEllipseItem, QGraphicsTextItem,QGraphicsRectItem
import sys
def visualize_tree_pyqt(node):
    class TreeVisualizer(QGraphicsView):
        def __init__(self, root_node):
            super().__init__()
            self.scene = QGraphicsScene()
            self.setScene(self.scene)
            self.setWindowTitle("Tree Visualization")
            self.setRenderHint(QPainter.Antialiasing)

            self.node_padding = 10  # Padding around the text
            self.h_spacing = 120
            self.v_spacing = 100
            self.positions = {}
            self.counter = {"x": 0}

            self.scale_factor = 1.0  # Initial zoom level
            self.zoom_factor = 1.1  # Zoom step (10%)

            self.draw_tree(root_node)
            self.setSceneRect(self.scene.itemsBoundingRect())
            self.setMinimumSize(800, 600)

        def draw_tree(self, node):
            self.traverse_and_place(node)
            for nid, (x, y, data) in self.positions.items():
                self.draw_node(x, y, data["root"])
                parent_id = data.get("parent_id")
                if parent_id:
                    px, py, _ = self.positions[parent_id]
                    self.draw_edge(px, py, x, y)

        def traverse_and_place(self, node, depth=0, parent_id=None):
            nid = id(node)
            x = self.counter["x"] * self.h_spacing
            y = depth * self.v_spacing
            self.positions[nid] = (x, y, {"root": node["root"], "parent_id": parent_id})
            self.counter["x"] += 1
            for child in node.get("children", []):
                self.traverse_and_place(child, depth + 1, nid)

        def draw_node(self, x, y, text):
            # Create a text item to get its bounding rect
            text_item = QGraphicsTextItem(text)
            text_item.setFont(QFont("Consolas", 10, QFont.Bold))  # Font: Arial, Bold, size 10
            text_rect = text_item.boundingRect()

            # Adjust the size of the rectangle to fit the text (with padding)
            rect_width = text_rect.width() + self.node_padding * 2
            rect_height = text_rect.height() + self.node_padding * 2

            # Create the rectangle (node) with blue color
            rect = QGraphicsRectItem(
                x - rect_width / 2,  # Center the rectangle
                y - rect_height / 2,  # Center the rectangle
                rect_width,
                rect_height
            )
            rect.setBrush(QBrush(QColor("#6BBF6A")))  # Set the color to blue
            rect.setPen(QPen(QColor("#4C4C4C"), 2))  # Black border, width 2
            self.scene.addItem(rect)

            # Create the text item and position it in the center of the rectangle
            text_item.setPos(x - text_rect.width() / 2, y - text_rect.height() / 2)
            text_item.setDefaultTextColor(QColor(255, 255, 255))  # White font color
            self.scene.addItem(text_item)

        def draw_edge(self, x1, y1, x2, y2):
            start_x = x1  # 父节点的x坐标
            start_y = y1 + self.node_padding * 2  # 父节点的下边中点，向下延伸
            mid_x = x2  # 子节点的x坐标
            mid_y = y2 - self.node_padding * 2   # 子节点矩形的上边中点
            path = QPainterPath()
            path.moveTo(start_x, start_y)
            path.lineTo(start_x, start_y + 20) 
            path.lineTo(mid_x, start_y + 20) 
            path.lineTo(mid_x, mid_y)
            self.scene.addPath(path, QPen(QColor(0, 0, 0), 2, Qt.SolidLine))  # 黑色线条，宽度2

        def wheelEvent(self, event):
            # Handle zooming with the mouse wheel
            angle = event.angleDelta().y()  # Get the scroll direction (positive for zoom in, negative for zoom out)
            if angle > 0:
                # Zoom in
                self.scale(self.zoom_factor, self.zoom_factor)
                self.scale_factor *= self.zoom_factor
            else:
                # Zoom out
                self.scale(1 / self.zoom_factor, 1 / self.zoom_factor)
                self.scale_factor /= self.zoom_factor

            # Set zoom limits
            if self.scale_factor < 0.1:
                self.scale_factor = 0.1
            elif self.scale_factor > 5:
                self.scale_factor = 5

            # Optional: Prevent the scene from being zoomed out too much or zoomed in too much
            if self.scale_factor < 0.1 or self.scale_factor > 5:
                return

            event.accept()  # Accept the event

    # Run the application
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