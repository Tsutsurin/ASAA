import logging

import pandas as pd

from api_client import enrich_params_with_api
from config import Settings

logger = logging.getLogger('auto_responsible.service')


def normalize_value(value) -> str:
    if pd.isna(value):
        return ''

    return str(value).strip()


def get_responsibles_stub(params: pd.DataFrame) -> pd.DataFrame:
    result = params.copy()

    result['group'] = 'TEST_GROUP'
    result['leader_email'] = ''
    result['emails'] = 'test@company.ru'

    logger.info('Используется заглушка вместо API')

    return result


def get_unique_params(params: pd.DataFrame) -> pd.DataFrame:
    unique_params = params.copy()

    unique_params['fqdn'] = unique_params['fqdn'].apply(normalize_value)
    unique_params['ip'] = unique_params['ip'].apply(normalize_value)

    unique_params = unique_params[
        (unique_params['fqdn'] != '')
        | (unique_params['ip'] != '')
    ]

    unique_params = unique_params.drop_duplicates(
        subset=[
            'fqdn',
            'ip',
        ],
        keep='first',
    )

    return unique_params.reset_index(drop=True)


def enrich_with_responsibles(
    params: pd.DataFrame,
    settings: Settings,
) -> pd.DataFrame:
    if params.empty:
        logger.warning('Пустой набор входных параметров')
        return params

    unique_params = get_unique_params(params)

    logger.info(
        'Строк во входном отчете: %s | уникальных fqdn/ip для API: %s',
        len(params),
        len(unique_params),
    )

    if unique_params.empty:
        logger.warning('После дедупликации не осталось fqdn/ip')
        return unique_params

    if not settings.api.enabled:
        return get_responsibles_stub(unique_params)

    return enrich_params_with_api(
        params=unique_params,
        settings=settings.api,
    )