import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

TEMP_DIR = BASE_DIR / 'temp'
TEMP_DIR.mkdir(exist_ok=True)

LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)


@dataclass
class EwsSettings:
    enabled: bool
    service_endpoint: str
    username: str
    password_env: str
    password: str
    email: str
    auth_type: str
    verify_ssl: bool


@dataclass
class ApiSettings:
    enabled: bool
    base_url: str
    verify_ssl: bool
    timeout: int


@dataclass
class SendEmailSettings:
    enabled: bool
    to: str
    cc: str | None
    subject: str
    body: str


@dataclass
class RecipientFilterSettings:
    enabled: bool
    ldap_server: str
    ldap_user: str
    ldap_password_env: str
    ldap_password: str
    search_base: str
    max_recipients: int
    fallback_to: str
    fallback_cc: str | None
    allowed_titles: list[str]
    blacklist_file: str | None


@dataclass
class DispatchSettings:
    enabled: bool
    template_path: str
    no_group_template_path: str
    service_template_path: str
    to: str
    cc: str | None
    no_group_to: str
    no_group_cc: str | None
    subject: str
    no_group_subject: str
    output_dir: str
    network_tasks_dir: str
    registry_file: str
    registry_columns: dict[str, str]
    group_column: str
    ip_column: str
    fqdn_column: str
    vulnerability_column: str
    placeholder: str
    status_value: str
    max_emails_per_run: int
    pause_between_emails_seconds: int
    recipient_filter: RecipientFilterSettings
    service_routing: str
    attachment_drop_columns: list[str]


@dataclass
class SearchDirectorySettings:
    enabled: bool
    input_dir: str
    output_dir: str
    archive_dir: str | None
    delete_after_processing: bool


@dataclass
class DispatchDirectorySettings:
    enabled: bool
    input_dir: str
    archive_dir: str | None
    error_dir: str | None
    delete_after_processing: bool


@dataclass
class Settings:
    enrich_folder: str
    subject_contains: str | None
    only_unread: bool
    ews: EwsSettings
    api: ApiSettings
    send_email: SendEmailSettings
    dispatch: DispatchSettings
    search_directory: SearchDirectorySettings
    dispatch_directory: DispatchDirectorySettings
    backend_mapping_file: str | None
    report_formatter_config: str
    columns_config: str


def _load_password(env_var: str) -> str:
    password = os.getenv(env_var, '')

    if not password:
        raise ValueError(
            f'Не найдена переменная окружения с паролем: {env_var}'
        )

    return password


def load_settings(path: str | Path | None = None) -> Settings:
    if path is None:
        path = BASE_DIR / 'config' / 'settings.json'
    else:
        path = BASE_DIR / path

    with open(path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    ews = data['ews']
    api = data['api']
    send_email = data['send_email']
    dispatch = data['dispatch']
    recipient_filter = dispatch['recipient_filter']

    return Settings(
        enrich_folder=data['enrich_folder'],
        subject_contains=data.get('subject_contains'),
        only_unread=data['only_unread'],
        ews=EwsSettings(
            enabled=ews.get('enabled', True),
            service_endpoint=ews['service_endpoint'],
            username=ews['username'],
            password_env=ews['password_env'],
            password=_load_password(ews['password_env']),
            email=ews['email'],
            auth_type=ews.get('auth_type', 'NTLM'),
            verify_ssl=ews.get('verify_ssl', True),
        ),
        api=ApiSettings(
            enabled=api.get('enabled', True),
            base_url=api['base_url'],
            verify_ssl=api.get('verify_ssl', True),
            timeout=api.get('timeout', 30),
        ),
        send_email=SendEmailSettings(
            enabled=send_email.get('enabled', False),
            to=send_email['to'],
            cc=send_email.get('cc'),
            subject=send_email['subject'],
            body=send_email['body'],
        ),
        dispatch=DispatchSettings(
            enabled=dispatch.get('enabled', True),
            template_path=dispatch['template_path'],
            no_group_template_path=dispatch['no_group_template_path'],
            service_template_path=dispatch['service_template_path'],
            to=dispatch['to'],
            cc=dispatch.get('cc'),
            no_group_to=dispatch['no_group_to'],
            no_group_cc=dispatch.get('no_group_cc'),
            subject=dispatch['subject'],
            no_group_subject=dispatch['no_group_subject'],
            output_dir=dispatch['output_dir'],
            network_tasks_dir=dispatch['network_tasks_dir'],
            registry_file=dispatch['registry_file'],
            registry_columns=dispatch['registry_columns'],
            group_column=dispatch['group_column'],
            ip_column=dispatch['ip_column'],
            fqdn_column=dispatch['fqdn_column'],
            vulnerability_column=dispatch['vulnerability_column'],
            placeholder=dispatch['placeholder'],
            status_value=dispatch['status_value'],
            max_emails_per_run=dispatch.get('max_emails_per_run', 0),
            pause_between_emails_seconds=dispatch.get(
                'pause_between_emails_seconds',
                0,
            ),
            recipient_filter=RecipientFilterSettings(
                enabled=recipient_filter.get('enabled', False),
                ldap_server=recipient_filter['ldap_server'],
                ldap_user=recipient_filter['ldap_user'],
                ldap_password_env=recipient_filter['ldap_password_env'],
                ldap_password=_load_password(
                    recipient_filter['ldap_password_env'],
                ),
                search_base=recipient_filter['search_base'],
                max_recipients=recipient_filter.get('max_recipients', 0),
                fallback_to=recipient_filter['fallback_to'],
                fallback_cc=recipient_filter.get('fallback_cc'),
                allowed_titles=recipient_filter.get(
                    'allowed_titles',
                    [],
                ),
                blacklist_file=recipient_filter.get('blacklist_file'),
            ),
            service_routing=dispatch.get('service_routing', ''),
            attachment_drop_columns=dispatch.get(
                'attachment_drop_columns',
                [],
            ),
        ),
        search_directory=SearchDirectorySettings(
            enabled=data['search_directory'].get('enabled', False),
            input_dir=data['search_directory']['input_dir'],
            output_dir=data['search_directory']['output_dir'],
            archive_dir=data['search_directory'].get('archive_dir'),
            delete_after_processing=data['search_directory'].get(
                'delete_after_processing',
                False,
            ),
        ),
        dispatch_directory=DispatchDirectorySettings(
            enabled=data['dispatch_directory'].get('enabled', False),
            input_dir=data['dispatch_directory']['input_dir'],
            archive_dir=data['dispatch_directory'].get('archive_dir'),
            error_dir=data['dispatch_directory'].get('error_dir'),
            delete_after_processing=data['dispatch_directory'].get(
                'delete_after_processing',
                False,
            ),
        ),
        backend_mapping_file=data.get('backend_mapping_file'),
        report_formatter_config=data.get(
            'report_formatter_config',
            'config/config.ini',
        ),
        columns_config=data.get('columns_config', 'config/columns.json'),
    )


def load_columns(path: str | Path | None = None) -> dict[str, list[str]]:
    if path is None:
        path = BASE_DIR / 'config' / 'columns.json'
    else:
        path = BASE_DIR / path

    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file)