from pathlib import Path


def load_html_template(template_path: Path) -> str:
    with open(template_path, 'r', encoding='utf-8') as file:
        return file.read()


def render_html_template(
    template_path: Path,
    placeholder: str,
    group_name: str,
) -> str:
    html = load_html_template(template_path)

    return html.replace(
        placeholder,
        group_name,
    )