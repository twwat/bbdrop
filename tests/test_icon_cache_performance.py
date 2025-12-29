"""
Test script to demonstrate icon cache performance improvement.

This script simulates the startup scenario where 989 gallery rows each load
multiple icons, demonstrating the ~10,000 disk I/O operation reduction.
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
from src.gui.icon_manager import IconManager


def simulate_gallery_loading(icon_manager: IconManager, num_galleries: int = 989):
    """
    Simulate loading icons for multiple gallery rows.

    Args:
        icon_manager: IconManager instance
        num_galleries: Number of gallery rows to simulate
    """
    print(f"\n{'='*60}")
    print(f"SIMULATING {num_galleries} GALLERY ROWS LOADING")
    print(f"{'='*60}\n")

    # Icons loaded per gallery row
    icons_per_row = [
        # ActionButtonWidget icons (4 total)
        'action_start',
        'action_stop',
        'action_view',
        'action_cancel',

        # FileHostsStatusWidget icons (assume 10 hosts for worst-case)
        'host_enabled', 'host_disabled',
        'action_view', 'action_view', 'action_view',
        'action_view', 'action_view', 'action_view',
        'action_view', 'action_view'
    ]

    start_time = time.time()

    # Simulate loading each gallery row
    for gallery_num in range(1, num_galleries + 1):
        for icon_name in icons_per_row:
            # Load icon (will hit cache after first gallery)
            icon_manager.get_icon(icon_name)

        # Progress indicator
        if gallery_num % 100 == 0:
            elapsed = time.time() - start_time
            print(f"  Loaded {gallery_num}/{num_galleries} galleries "
                  f"({elapsed:.2f}s elapsed)")

    elapsed_time = time.time() - start_time

    # Get and display cache statistics
    stats = icon_manager.get_cache_stats()

    print(f"\n{'='*60}")
    print("PERFORMANCE RESULTS")
    print(f"{'='*60}")
    print(f"Galleries loaded:      {num_galleries:,}")
    print(f"Time elapsed:          {elapsed_time:.2f} seconds")
    print(f"Icons per gallery:     {len(icons_per_row)}")
    print(f"Total icon requests:   {stats['hits'] + stats['misses']:,}")
    print()
    print(f"Cache hits:            {stats['hits']:,}")
    print(f"Cache misses:          {stats['misses']:,}")
    print(f"Disk I/O operations:   {stats['disk_loads']:,}")
    print(f"Cached unique icons:   {stats['cached_icons']:,}")
    print(f"Cache hit rate:        {stats['hit_rate']:.2f}%")
    print()
    print(f"💾 Disk I/O SAVED:      {stats['hits']:,} operations")
    print(f"⚡ Time per gallery:    {elapsed_time/num_galleries*1000:.2f}ms")
    print()

    # Calculate expected improvement
    expected_total_loads = num_galleries * len(icons_per_row)
    expected_cache_saves = expected_total_loads - stats['disk_loads']
    efficiency = (expected_cache_saves / expected_total_loads) * 100

    print(f"EFFICIENCY ANALYSIS")
    print(f"{'='*60}")
    print(f"Without cache:         {expected_total_loads:,} disk operations")
    print(f"With cache:            {stats['disk_loads']:,} disk operations")
    print(f"Reduction:             {expected_cache_saves:,} operations ({efficiency:.1f}%)")
    print()

    # Estimate time saved (assuming ~5ms per disk I/O)
    time_saved = expected_cache_saves * 0.005  # 5ms per disk read
    print(f"Estimated time saved:  {time_saved:.2f} seconds")
    print(f"{'='*60}\n")


def main():
    """Run the icon cache performance test."""
    # Initialize Qt application
    app = QApplication(sys.argv)

    # Initialize IconManager
    assets_dir = Path(__file__).parent.parent / "assets"
    if not assets_dir.exists():
        print(f"Error: Assets directory not found: {assets_dir}")
        return 1

    icon_manager = IconManager(str(assets_dir))

    print("\n" + "="*60)
    print("ICON CACHE PERFORMANCE TEST")
    print("Testing icon caching for 989 gallery rows")
    print("="*60)

    # Run simulation with 989 galleries (realistic scenario)
    simulate_gallery_loading(icon_manager, num_galleries=989)

    # Also test with smaller set for comparison
    print("\n\nCOMPARISON: Running with 100 galleries...")
    icon_manager.refresh_cache()  # Clear cache for fair comparison
    simulate_gallery_loading(icon_manager, num_galleries=100)

    return 0


if __name__ == '__main__':
    sys.exit(main())
