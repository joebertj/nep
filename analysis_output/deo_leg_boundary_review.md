# DEO–LEG boundary crosswalk: initial evidence review

## Outputs

- `deo_leg_boundary_crosswalk.json` and CSV contain 984 positive-area polygon
  intersections from 203 DEO and 245 LEG features. Touching alone is excluded.
- 194 intersections meet the documented small-intersection review threshold.
  The other 790 exceed that threshold; this does not verify legal coverage.
- 1,668 municipal source labels were imported separately into PH location DB.
- Existing PDF claims and boundary intersections can be inspected together with
  `python3 location_data/query_locations.py --deo 'Bulacan 1st DEO'`.

## Findings requiring care

1. The LEG file contains Bulacan First through Fourth Districts, while existing
   reference claims include Fifth and Sixth. The file cannot be treated as the
   complete FY2027 district configuration.
2. Butuan City DEO primarily intersects a polygon labeled Agusan del Norte First
   District. That historical source label must not silently become the current
   Butuan Lone District identity.
3. Neighboring provinces have positive-area intersections too. For example,
   Bulacan 2nd DEO intersects the polygon labeled Rizal Second District. Whether
   this is a boundary mismatch or real administrative coverage needs independent
   confirmation; area alone cannot establish it.
4. Misamis Occidental First District has no intersection exceeding the review
   threshold. This is a source/geometry coverage issue to investigate, not proof
   that the district has no DEO coverage.
5. One DEO and one LEG geometry needed reconstruction/repair. Raw source geometry
   stays unchanged in the archive, and derived repair flags are retained.
6. Municipal alias lookup retains multiple place candidates where geographic
   levels or identities conflict. It does not merge municipality/city/locality
   records just to increase the resolved count.

## Attribution policy

This build enriches the evidence database, not public allocation totals. Source
copyright and edit dates do not establish effective legal boundary dates.
All effective dates remain unknown. Boundary areas are not allocation weights.
Project geometry and funded segment scope remain necessary for strict LEG
attribution. Multi-place projects without a supported split remain unresolved.

Reconcile old/new district identities, qualified municipal coverage and boundary
disagreements before promoting any of this evidence into current memberships.
The reusable overlay is local-only; the regular database builder imports its
generated output without needing Shapely.
