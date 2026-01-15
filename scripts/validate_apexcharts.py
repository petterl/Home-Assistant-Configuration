#!/usr/bin/env python3
"""Validate apexcharts-card configurations in Lovelace dashboards"""
import yaml
import sys
import re

def find_apexcharts_cards(obj, path=""):
    """Find all apexcharts-card configurations"""
    cards = []
    if isinstance(obj, dict):
        if obj.get('type') == 'custom:apexcharts-card':
            cards.append((path, obj))
        for k, v in obj.items():
            cards.extend(find_apexcharts_cards(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            cards.extend(find_apexcharts_cards(item, f"{path}[{i}]"))
    return cards

def validate_card(path, card):
    """Validate a single apexcharts-card configuration"""
    issues = []
    
    # Check required fields
    if 'series' not in card:
        issues.append(f"Missing 'series' field")
    
    # Check series configurations
    for i, series in enumerate(card.get('series', [])):
        series_path = f"series[{i}]"
        
        # Check entity exists
        if 'entity' not in series:
            issues.append(f"{series_path}: Missing 'entity'")
        
        # Check data_generator syntax
        if 'data_generator' in series:
            dg = series['data_generator']
            series_type = series.get('type', 'line')
            # scatter + data_generator often fails
            if series_type == 'scatter':
                issues.append(f"{series_path}: scatter type with data_generator may cause errors - use line type instead")
            # Check for common JS issues
            if '||' in dg and '??' not in dg:
                # Using || with potentially falsy values
                pass
            if 'entity.attributes' in dg:
                # Check if attributes access is safe
                if 'entity.attributes.' in dg and '|| ' not in dg and '?? ' not in dg and '?.':
                    issues.append(f"{series_path}: data_generator accesses entity.attributes without null check")
        
        # Check transform syntax
        if 'transform' in series:
            transform = series['transform']
            if 'hass.states' in transform and 'parseFloat' not in transform and '.state' in transform:
                issues.append(f"{series_path}: transform uses .state without parseFloat (string subtraction)")
    
    # Check apex_config for known issues
    apex = card.get('apex_config', {})
    if apex:
        # Check dataLabels formatter
        dl = apex.get('dataLabels', {})
        if 'formatter' in dl:
            fmt = dl['formatter']
            if isinstance(fmt, str) and fmt.startswith('EVAL:'):
                issues.append(f"apex_config.dataLabels.formatter uses 'EVAL:' prefix - may not be supported in all versions")
    
    # Check yaxis configuration
    if 'yaxis' in card:
        for i, y in enumerate(card['yaxis']):
            if 'id' in y:
                yaxis_id = y['id']
                # Check if any series references this yaxis_id
                for j, s in enumerate(card.get('series', [])):
                    if s.get('yaxis_id') == yaxis_id:
                        break
                else:
                    # No series uses this yaxis
                    pass
    
    return issues

# Load dashboard
with open(sys.argv[1]) as f:
    dashboard = yaml.safe_load(f)

cards = find_apexcharts_cards(dashboard)
print(f"Found {len(cards)} apexcharts-card(s)\n")

all_issues = []
for path, card in cards:
    title = card.get('header', {}).get('title', 'Untitled')
    print(f"Card: {title}")
    print(f"  Path: {path}")
    issues = validate_card(path, card)
    if issues:
        print(f"  Issues found:")
        for issue in issues:
            print(f"    - {issue}")
        all_issues.extend(issues)
    else:
        print(f"  No issues detected")
    print()

if all_issues:
    print(f"\nTotal: {len(all_issues)} potential issue(s) found")
    sys.exit(1)
else:
    print("All cards validated successfully")
