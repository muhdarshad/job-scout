"""One synchronized terminal display for scraping and final counts."""
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table


class ScrapeDisplay:
    def __init__(self, enabled=True):
        self.console = Console()
        self.progress = Progress(SpinnerColumn(), TextColumn('{task.description}'), BarColumn(),
                                 TextColumn('{task.fields[stage]}'), TimeElapsedColumn(),
                                 console=self.console, disable=not enabled)

    def __enter__(self):
        self.progress.start()
        return self

    def __exit__(self, *args):
        self.progress.stop()

    def add(self, name):
        return self.progress.add_task(name, total=None, stage='Queued')

    def update(self, task, stage, completed=None, total=None):
        self.progress.update(task, stage=stage, completed=completed, total=total)


def print_summary(stats):
    table = Table(title='Scraping results')
    for name in ['Source / website', 'Found*', 'After titles', 'Ranked / new', 'Likely interested', 'Status']:
        table.add_column(name, min_width=16 if name == 'Source / website' else None, justify='left' if name in {'Source / website', 'Status'} else 'right')
    for row in stats:
        table.add_row(row['source_site'], *(str(row.get(k, 0)) for k in ['found', 'after_titles', 'ranked', 'interesting']), row['status'])
    table.add_row('TOTAL', *(str(sum(r.get(k, 0) for r in stats)) for k in ['found', 'after_titles', 'ranked', 'interesting']), end_section=True)
    console = Console()
    console.print(table)
    console.print('*Found: rows returned by adapters; includes repeated LS searches. Portal adapters may already apply date, country, and title filters.')
    for row in stats:
        for error in row.get('errors', []):
            console.print(f"{row['source_site']}: {error}", markup=False)

