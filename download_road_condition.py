#!/usr/bin/env python3
"""JSON archive of every advertised road-condition layer and table."""
from download_arcgis_inventory import main

if __name__ == '__main__':
    main(selected_service='Road_Condition_with_No_Assessment/FeatureServer', profile='road_condition')
