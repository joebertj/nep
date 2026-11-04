Historical House portrait research, 4 November 2026
=================================================

The preserved HTML snapshots are Wikipedia's district roster tables for the
16th, 17th, 18th and 19th Congresses:

- https://en.wikipedia.org/wiki/16th_Congress_of_the_Philippines
- https://en.wikipedia.org/wiki/17th_Congress_of_the_Philippines
- https://en.wikipedia.org/wiki/18th_Congress_of_the_Philippines
- https://en.wikipedia.org/wiki/19th_Congress_of_the_Philippines

Commons image metadata was collected through
https://commons.wikimedia.org/w/api.php using `generator=search`, namespace 6,
`prop=imageinfo`, and `iiprop=url|extmetadata`. Searches included
`intitle:"17th Congress"`, `"17th Congress" "House"`, the corresponding searches
for the other terms, and `"congress.gov.ph/members/" "2016"` / `"2019"`.
Each response preserves the actual original source, creator and license.
Most portraits originate from the House of Representatives, with archived
official profile links retained in Commons' Credit metadata.

`biography-portraits.json` preserves Wikipedia pageimages results for remaining
historical members, together with the corresponding Commons image metadata.
Only freely licensed Commons images were requested. Unlinked ambiguous names
require an official House creator; landscape/group images and flags/logos are
excluded. No deleted Commons images are recovered from mirrors.

Historical identities are matched by a unique roster name or an explicit
province AND district in the official portrait caption for that Congress.
Biographies and original image descriptions remain linked for review.
The Congress of the person's service is distinct from the photograph's Congress:
a verified portrait of the same individual can illustrate another term.

Wikimedia requests are throttled. The preferred cached 250-pixel thumbnail
endpoint is used in place of repeated full-size original downloads. Original
image URLs remain in the verification manifest and public audit.

Rebuild discovery and image verification with:

    python3 research_historical_congress_photos.py --download --missing-people-only

The research utility requires BeautifulSoup; the report builder consumes the
resulting external JSON and requires no HTML parser or network requests.
Wikipedia/Commons text snapshots retain their source attribution and applicable
CC BY-SA terms. Images carry their individual creators and licenses.
