#!/usr/bin/env python3
"""JSON archive of every advertised city/municipal boundary layer and table."""
from download_arcgis_inventory import main
if __name__=='__main__':
    main(selected_service='City_Municipal_Boundaries/FeatureServer',profile='city_municipal_boundaries')
