#!/usr/bin/env python3
"""JSON archive of every advertised FY2025 DA FMR live-view layer and table."""
from download_arcgis_inventory import main
if __name__=='__main__':
    main(selected_service='DA_FMR_FY2025_LiveView/FeatureServer',profile='da_fmr_fy2025')
