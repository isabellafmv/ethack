"""
Render a clean, empty 3D coordinate system with the three pillar axes labeled.
No data points — just the space, for the "introduce the axes" beat of the pitch.

Requirements:
    pip install matplotlib --break-system-packages

Outputs:
    empty_axes.png — transparent background, ready to drop into Canva/PowerPoint
"""

import matplotlib.pyplot as plt
import numpy as np

fig = plt.figure(figsize=(11, 8.5))
ax = fig.add_subplot(111, projection="3d")

# Clean look: strip the entire default box/pane/grid frame, keep only
# the custom arrows drawn below
ax.set_facecolor("none")
fig.patch.set_alpha(0)
ax.set_axis_off()

# Axis lines drawn manually as full-length shafts with a small arrowhead
# cone at the tip (more reliable across matplotlib versions than quiver's
# built-in arrowhead, which can render too small to see at this scale)
lim = 1.3
axis_color = "#333333"
arrow_kwargs = dict(color=axis_color, linewidth=1.8)

axis_ends = [
    (lim, 0, 0),   # P1
    (0, lim, 0),   # P2
    (0, 0, lim),   # P3
]
for x, y, z in axis_ends:
    ax.plot([0, x], [0, y], [0, z], **arrow_kwargs)
    ax.quiver(
        x * 0.92, y * 0.92, z * 0.92, x * 0.08, y * 0.08, z * 0.08,
        color=axis_color, arrow_length_ratio=1.0, linewidth=1.8,
    )

ax.set_xlim(-0.2, lim)
ax.set_ylim(-0.2, lim)
ax.set_zlim(-0.2, lim)

# Axis labels — swap wording here if you tweak pillar names later
label_kwargs = dict(fontsize=14, fontweight="bold", color="#222222", ha="center")
ax.text(lim + 0.25, 0, -0.1, "P1\nResource & Operational\nEfficiency", **label_kwargs)
ax.text(0, lim + 0.25, -0.1, "P2\nStructural / Disruption\nRisk", **label_kwargs)
ax.text(0, 0, lim + 0.25, "P3\nGovernance & Capital\nStewardship", **label_kwargs)

ax.view_init(elev=18, azim=45)  # good default viewing angle — adjust to taste
ax.set_box_aspect([1, 1, 1])

# Generous margins so labels never clip, regardless of bbox_inches behavior
ax.set_xlim(-0.3, lim + 0.9)
ax.set_ylim(-0.3, lim + 0.9)
ax.set_zlim(-0.3, lim + 0.9)

plt.savefig("empty_axes.png", dpi=300, transparent=True, pad_inches=0.3)
print("Saved empty_axes.png")