-- SQLite
UPDATE plants SET monthly_temps_json  = '{
"jan": {"avg": 14, "high": 21, "low": 8},
    "feb": {"avg": 14, "high": 21, "low": 8},
    "mar": {"avg": 17, "high": 25, "low": 10},
    "apr": {"avg": 19, "high": 27, "low": 11},
    "may": {"avg": 19, "high": 27, "low": 11},
    "jun": {"avg": 20, "high": 27, "low": 13},
    "jul": {"avg": 18, "high": 22, "low": 13},
    "aug": {"avg": 17, "high": 22, "low": 13},
    "sep": {"avg": 18, "high": 22, "low": 13},
    "oct": {"avg": 16, "high": 21, "low": 11},
    "nov": {"avg": 15, "high": 21, "low": 10},
    "dec": {"avg": 15, "high": 21, "low": 9}
  }' WHERE plant_id = 'plant_c5ab40d4';