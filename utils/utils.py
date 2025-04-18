# import matplotlib.pyplot as plt
import sys
from PyQt5.QtWidgets import (
    QApplication,
    QGraphicsScene,
    QGraphicsView,
    QGraphicsEllipseItem,
    QGraphicsTextItem,
)
from PyQt5.QtGui import QPen, QBrush, QPainter
from PyQt5.QtCore import Qt


def visualize_tree_pyqt(node):
    class TreeVisualizer(QGraphicsView):
        def __init__(self, root_node):
            super().__init__()
            self.scene = QGraphicsScene()
            self.setScene(self.scene)
            self.setWindowTitle("Tree Visualization")
            self.setRenderHint(QPainter.Antialiasing)

            self.node_radius = 30
            self.h_spacing = 80
            self.v_spacing = 80
            self.positions = {}
            self.counter = {"x": 0}

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
            ellipse = QGraphicsEllipseItem(
                x - self.node_radius,
                y - self.node_radius,
                self.node_radius * 2,
                self.node_radius * 2,
            )
            ellipse.setBrush(QBrush(Qt.white))
            ellipse.setPen(QPen(Qt.black))
            self.scene.addItem(ellipse)

            text_item = QGraphicsTextItem(text)
            text_rect = text_item.boundingRect()
            text_item.setPos(x - text_rect.width() / 2, y - text_rect.height() / 2)
            self.scene.addItem(text_item)

        def draw_edge(self, x1, y1, x2, y2):
            self.scene.addLine(
                x1, y1 + self.node_radius, x2, y2 - self.node_radius, QPen(Qt.black)
            )

    # 支持在已有的 QApplication 中运行
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
