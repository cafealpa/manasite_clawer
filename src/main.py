import sys
import argparse
import time
import threading
from ui.main_window import MainWindow
from core.engine import CrawlerEngine
from utils.logger import logger
from data.db_repository import db

def run_cli(url, output_dir, threads):
    print(f"Starting CLI Crawler...")
    print(f"URL: {url}")
    print(f"Output: {output_dir}")
    print(f"Threads: {threads}")
    
    # Configure logger to output to console only (already default? verify logger)
    # The current logger prints to console, but we might want to ensure it doesn't try to queue to GUI if GUI isn't there.
    # Our simple logger prints to stdout, so it's fine.

    engine = CrawlerEngine(download_path=output_dir, num_download_threads=threads)
    
    # We need to keep the main thread alive while engine runs in background or run engine synchronously.
    # Engine.start is blocking? No, engine.start calls logic. 
    # Let's check engine.start.
    # engine.start() calls _init_driver, then _get_episode_list, etc.
    # It does NOT spawn a thread for itself, it runs in the caller's thread logic-wise?
    # Wait, MainWindow spawns a thread to call engine.start.
    # So engine.start IS blocking. Perfect.
    
    try:
        engine.start(url)
    except KeyboardInterrupt:
        print("\nStopping crawler...")
        engine.stop()

def main():
    parser = argparse.ArgumentParser(description="Manatoki Crawler CLI")
    parser.add_argument("--url", type=str, help="Target URL to crawl (e.g., https://manatoki.net/comic/123)")
    parser.add_argument("-o", "--output", type=str, default="downloaded_files", help="Download directory path")
    parser.add_argument("-t", "--threads", type=int, default=4, help="Number of download threads")
    parser.add_argument("--db-path", type=str, help="Path to database file")
    parser.add_argument("--gui", action="store_true", help="Launch the GUI application")
    
    args = parser.parse_args()

    # Apply DB Path if provided
    if args.db_path:
        db.db_path = args.db_path

    # Case 1: No arguments provided OR --gui flag -> GUI Mode
    if len(sys.argv) == 1 or args.gui:
        app = MainWindow()
        app.mainloop()
        return

    # Case 2: CLI Mode
    if args.url:
        run_cli(args.url, args.output, args.threads)
    else:
        # If arguments are provided but not --url and not --gui (e.g. just --output), show help
        print("Error: --url is required for CLI mode.")
        parser.print_help()

if __name__ == "__main__":
    main()
