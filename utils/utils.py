import matplotlib.pyplot as plt

def serialize_token(token):
    return {
        key: (value.name if hasattr(value, 'name') else value)
        for key, value in token.items()
    }

def print_tree(node, indent=0):
    print("  " * indent + str(node["root"]))
    for child in node.get("children", []):
        print_tree(child, indent + 1)

def visualize_tree_matplotlib(node):
    fig, ax = plt.subplots()
    ax.axis('off')

    positions = {}  # 节点 id -> (x,y)
    nodes = {}      # 节点 id -> node dict
    edges = []      # list of (parent_id, child_id)
    counter = {'x': 0}

    def traverse(n, depth=0):
        nid = id(n)
        x = counter['x']
        y = -depth
        positions[nid] = (x, y)
        nodes[nid] = n
        counter['x'] += 1
        for child in n.get('children', []):
            edges.append((nid, id(child)))
            traverse(child, depth + 1)

    traverse(node)

    for pid, cid in edges:
        x1, y1 = positions[pid]
        x2, y2 = positions[cid]
        ax.plot([x1, x2], [y1, y2], linewidth=1)

    for nid, (x, y) in positions.items():
        ax.text(x, y, nodes[nid]['root'],
                ha='center', va='center',
                bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='black', lw=0.8))

    plt.tight_layout()
    plt.show()