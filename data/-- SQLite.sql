-- SQLite
UPDATE plants SET monthly_temps_josn  = '{
    "jan": {"avg": 24, "high": 28, "low": 16},
    "feb": {"avg": 24, "high": 29, "low": 16},
    "mar": {"avg": 22, "high": 27, "low": 14},
    "apr": {"avg": 19, "high": 24, "low": 11},
    "may": {"avg": 17, "high": 21, "low": 9},
    "jun": {"avg": 13, "high": 18, "low": 6},
    "jul": {"avg": 13, "high": 18, "low": 5},
    "aug": {"avg": 14, "high": 19, "low": 5},
    "sep": {"avg": 17, "high": 21, "low": 8},
    "oct": {"avg": 19, "high": 25, "low": 10},
    "nov": {"avg": 20, "high": 23, "low": 11},
    "dec": {"avg": 22, "high": 27, "low": 14}
  }' WHERE id = 15;
  