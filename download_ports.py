#!/usr/bin/env python3
"""JSON archive of every advertised port layer and table."""
from download_arcgis_inventory import main
if __name__=='__main__':
    main(selected_service='Port/FeatureServer',profile='ports')
