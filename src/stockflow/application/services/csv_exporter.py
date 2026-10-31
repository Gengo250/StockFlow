"""Serialização reutilizável de relatórios tabulares em CSV."""

import csv


def export_csv(path, headers, rows) -> None:
    """Escreve CSV compatível com planilhas, preservando texto e acentuação."""

    def safe(value):
        text = str(value)
        if text.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + text
        return text

    with open(path, "w", encoding="utf-8-sig", newline="") as output:
        writer = csv.writer(output, delimiter=";")
        writer.writerow([safe(value) for value in headers])
        writer.writerows([safe(value) for value in row] for row in rows)
