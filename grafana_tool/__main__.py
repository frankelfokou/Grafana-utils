"""Entry point per `python -m grafana_tool`."""
import sys

from grafana_tool.cli import main

if __name__ == "__main__":
    sys.exit(main())
