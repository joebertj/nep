"""Keep prior POW rows when a replacement parse recovers no rows."""


def retain_prior_pow_rows(previous, incoming):
    if not previous or incoming.get('kind') != 'pow':
        return incoming

    current_rows = (incoming.get('pow') or {}).get('rows') or []
    if current_rows:
        incoming.pop('previousVersionPow', None)
        return incoming

    previous_rows = (previous.get('pow') or {}).get('rows') or []
    if previous_rows:
        retained = {
            'sha256': previous.get('sha256'),
            'version': previous.get('version'),
            'metadata': previous.get('metadata'),
            'pow': previous.get('pow'),
        }
    else:
        retained = previous.get('previousVersionPow')

    if retained and (retained.get('pow') or {}).get('rows'):
        incoming['previousVersionPow'] = retained
    return incoming
