#!/usr/bin/env python3
"""JSON archive of every advertised national road network layer and table."""
from download_arcgis_inventory import main
if __name__=='__main__':
    main(selected_service='National_Road_Network/FeatureServer',profile='national_road_network')
