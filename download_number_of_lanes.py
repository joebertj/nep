#!/usr/bin/env python3
"""JSON archive of every advertised number-of-lanes layer and table."""
from download_arcgis_inventory import main
if __name__=='__main__':
    main(selected_service='Number_of_Lanes/FeatureServer',profile='number_of_lanes')
