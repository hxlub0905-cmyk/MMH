"""Entry point for Combine Sample Measurement Tool.

Run:
    python tools/combine_sample_measurement/main.py

Workflow:
  Step 1  Load multiple (Excel + Image folder + KLARF) datasets
  Step 2  Re-run Laplacian quality check; auto/manual filter blurry images
  Step 3  Select Top-N by Min or Max CD; new sequential DID assigned
  Step 4  Export → KLARF (corrected coords) + Excel (enriched) + Overlay images
"""
import sys
from pathlib import Path

# Ensure project root is on the path before any MMH imports
_HERE        = Path(__file__).parent
_PROJECT_ROOT = _HERE.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from tools.combine_sample_measurement.gui.main_window import CombineSampleWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Combine Sample Measurement Tool")
    app.setApplicationVersion("1.0.0")

    # High-DPI support
    try:
        app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass

    window = CombineSampleWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
