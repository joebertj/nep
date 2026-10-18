#!/usr/bin/env python3
"""Dedicated JSON downloader for the selected detailed bridge inventory layer."""
from download_arcgis_inventory import main
if __name__=='__main__':
    main(selected_layer='Detailed_Bridge_Inventory_Final/FeatureServer/1',profile='bridge_inventory')
