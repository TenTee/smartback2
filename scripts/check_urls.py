import os
import django
from django.urls import get_resolver

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_back.settings')
django.setup()

def show_urls(url_list, depth=0):
    for entry in url_list:
        print("  " * depth + str(entry.pattern))
        if hasattr(entry, 'url_patterns'):
            show_urls(entry.url_patterns, depth + 1)

show_urls(get_resolver().url_patterns)
