"""
Standalone Biometric Sync Script

Runs locally to trigger a manual sync for a configured biometric device.
Pulls raw attendance data from the device, saves it to bm_raw_logs, and normalizes it.

Usage:
    python sync_device.py [--device-id DEVICE_UUID]
"""
import sys
import argparse
from sqlalchemy import select
from app.database.session import SessionLocal
from app.models.biometric.bm_device import BmDevice
from app.services.biometric.sync_engine import SyncEngine
from app.services.biometric.connection_profile_service import ConnectionProfileService


def run_standalone_sync(device_id_str: str = None):
    db = SessionLocal()
    try:
        # 1. Fetch devices
        if device_id_str:
            import uuid
            try:
                device_id = uuid.UUID(device_id_str)
            except ValueError:
                print(f"Error: Invalid UUID format for device-id '{device_id_str}'")
                sys.exit(1)
            device = db.scalar(select(BmDevice).where(BmDevice.id == device_id))
            if not device:
                print(f"Error: Device with ID '{device_id}' not found.")
                sys.exit(1)
        else:
            # Query first active device
            devices = db.scalars(select(BmDevice).where(BmDevice.is_active == True)).all()
            if not devices:
                print("Error: No active biometric devices found in the database.")
                print("Please configure a device in the UI first under 'Biometric Settings'.")
                sys.exit(1)
            
            if len(devices) == 1:
                device = devices[0]
            else:
                print("\nAvailable Biometric Devices:")
                for idx, dev in enumerate(devices):
                    print(f"  [{idx}] {dev.device_name} (Vendor: {dev.vendor}, ID: {dev.id})")
                
                try:
                    choice = input("\nSelect device index to sync [0]: ").strip()
                    choice_idx = int(choice) if choice else 0
                    device = devices[choice_idx]
                except (ValueError, IndexError):
                    print("Error: Invalid choice selection.")
                    sys.exit(1)

        print(f"\nInitializing sync for device: {device.device_name}...")
        print(f"Vendor: {device.vendor} | Timezone: {device.timezone}")

        # 2. Check Connection Profile
        profile_svc = ConnectionProfileService(db)
        profile = profile_svc.get_profile_for_device(device.id)
        if not profile:
            print(f"Error: No active Connection Profile found for device '{device.device_name}'.")
            print("Please configure connection profile settings in the UI first.")
            sys.exit(1)

        print(f"Connection Type: {profile.connection_type}")

        # 3. Instantiate SyncEngine & Run Sync
        print("Connecting to device and pulling logs... (This may take a moment)")
        engine = SyncEngine(db)
        result = engine.run_sync(device_id=device.id, sync_type="MANUAL")

        # 4. Print Results
        print("\n" + "=" * 40)
        print("            SYNC SUMMARY")
        print("=" * 40)
        print(f"Status:           {result.status}")
        print(f"Records Read:     {result.records_read}")
        print(f"Records Saved:    {result.records_saved}")
        print(f"Duplicates:       {result.duplicates_found}")
        print(f"Errors:           {result.errors_count}")
        print(f"Normalized logs:  {result.normalized_count}")
        print(f"Duration:         {result.duration_seconds:.2f} seconds")
        
        if result.error_message:
            print(f"Error Message:    {result.error_message}")
        print("=" * 40)
        
        if result.status == "SUCCESS":
            print("\nSync completed successfully! The frontend logs and live views are now populated.")
        else:
            print("\nSync completed with warnings/errors. Check logs for details.")

    except Exception as e:
        print(f"\nUnexpected error running sync: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Standalone Biometric Device Synchronization CLI")
    parser.add_argument("--device-id", help="UUID of the specific biometric device to sync")
    args = parser.parse_args()
    run_standalone_sync(args.device_id)
