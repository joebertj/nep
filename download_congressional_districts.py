#!/usr/bin/env python3
"""Dedicated JSON downloader for the selected congressional district polygons."""
from download_arcgis_inventory import main
if __name__=='__main__':
    main(selected_layer='Congressional_District/FeatureServer/0',profile='congressional_districts')
