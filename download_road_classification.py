#!/usr/bin/env python3
"""JSON archive of every advertised road classification layer and table."""
from download_arcgis_inventory import main
if __name__=='__main__':
    main(selected_service='Road_Classification/FeatureServer',profile='road_classification')
