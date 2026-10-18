#!/usr/bin/env python3
"""JSON archive of every advertised provincial boundary layer and table."""
from download_arcgis_inventory import main
if __name__=='__main__':
    main(selected_service='Provincial_Boundary/FeatureServer',profile='provincial_boundaries')
