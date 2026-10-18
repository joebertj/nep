#!/usr/bin/env python3
"""JSON archive of every advertised kilometer-post layer and table."""
from download_arcgis_inventory import main

if __name__ == '__main__':
    main(selected_service='Kilometer_Post/FeatureServer', profile='kilometer_posts')
