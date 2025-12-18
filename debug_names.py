
import os
import django
import sys

# Set up Django environment
sys.path.append('/Users/kdg/PATHDirectory/Git Repositories/seoulbusmap')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'busmap.settings')
django.setup()

from main.models import HangJeongDong

print("--- Checking HangJeongDong Names ---")
for hjd in HangJeongDong.objects.all()[:5]:
    print(f"Name: '{hjd.name}', District ID: {hjd.district_id}")

print("\n--- Checking Parsing Logic ---")
for hjd in HangJeongDong.objects.all()[:5]:
    parts = hjd.name.split(' ')
    if len(parts) > 1:
        print(f"Original: '{hjd.name}' -> Extracted: '{parts[1]}'")
    else:
        print(f"Original: '{hjd.name}' -> Extracted: '{hjd.name}' (No split)")
