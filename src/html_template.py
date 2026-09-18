"""Работа с HTML-шаблонами писем."""

from pathlib import Path


def render_html_template(
    template_path: str | Path,
    placeholder: str,
    value: str,
) -> str:
    template_path = Path(template_path)

    if not template_path.is_file():
        raise FileNotFoundError(
            f'HTML-шаблон не найден: {template_path}'
        )

    with open(
        template_path,
        'r',
        encoding='utf-8-sig',
    ) as file:
        html = file.read()

    placeholder = str(
        placeholder or ''
    )

    value = str(
        value or ''
    ).strip()

    if not placeholder:
        raise ValueError(
            'Placeholder для HTML-шаблона не задан'
        )

    return html.replace(
        placeholder,
        value,
    )