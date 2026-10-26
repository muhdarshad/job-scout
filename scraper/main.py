#!/usr/bin/env python
"""Scrape company portals and LS, then rank their combined results once."""
import argparse
from datetime import datetime
from pathlib import Path

from src.webscraper.pipeline import run_pipeline
from src.webscraper.config import OUTPUT_DIR
from src.webscraper.terminal import print_summary
from job_ranker_v2 import DEFAULT_OUTPUT_DIR, INTERESTED_REGEX, export_excel, next_output_path, rank_dataframe


def main():
    parser = argparse.ArgumentParser(description='Scrape and rank company portals and LS job boards')
    parser.add_argument('--max-results', type=int, help='Maximum returned jobs per company portal')
    parser.add_argument('--no-enrich', action='store_true', help='Skip portal enrichment and LinkedIn descriptions')
    parser.add_argument('--no-skills', action='store_true', help='Skip scraper skills extraction')
    parser.add_argument('--output', help='Combined CSV path')
    parser.add_argument('--config', help='Company sites YAML path')
    parser.add_argument('--ls-config', help='LS job board YAML path')
    parser.add_argument('--no-ls', action='store_true', help='Run company portals only')
    parser.add_argument('--workers', type=int, default=4, help='Concurrent company portals (default: 4)')
    parser.add_argument('--no-progress', action='store_true', help='Disable animated progress bars')
    parser.add_argument('--ranked-output-dir', default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    if args.workers < 1 or args.max_results is not None and args.max_results < 1:
        parser.error('--workers and --max-results must be positive')
    output = args.output or str(Path(OUTPUT_DIR) / f"jobs_{datetime.now():%Y%m%d_%H%M%S}.csv")
    df = run_pipeline(max_results_per_site=args.max_results, enrich=not args.no_enrich,
                      extract_skills=not args.no_skills, output_path=output, config_path=args.config,
                      workers=args.workers, include_ls=not args.no_ls, ls_config_path=args.ls_config,
                      progress=not args.no_progress)
    ranked = rank_dataframe(output, args.ranked_output_dir)
    stats = df.attrs['site_stats']
    for row in stats:
        kept = ranked[ranked['source_site'] == row['source_site']]
        row['ranked'] = len(kept)
        row['interesting'] = int(kept['title'].fillna('').map(lambda title: bool(INTERESTED_REGEX.search(title))).sum())
    print_summary(stats)
    print(f'Combined CSV: {output}')
    if not ranked.empty:
        path = next_output_path(args.ranked_output_dir)
        export_excel(ranked, path)
        print(f'Ranked workbook: {path}')
    else:
        print('No new jobs remain after ranking filters and history deduplication.')


if __name__ == '__main__':
    main()

