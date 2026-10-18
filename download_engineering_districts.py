#!/usr/bin/env python3
"""JSON archive of every advertised engineering district layer and table."""
from download_arcgis_inventory import main
if __name__=='__main__':
    main(selected_service='Engineering_District/FeatureServer',profile='engineering_districts')
