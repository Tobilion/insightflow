# InsightFlow

A modular, desktop-based data analysis utility built with Python and PySide6. InsightFlow provides a guided, step-by-step workflow for fetching and analyzing public financial data, demonstrating clean architectural patterns and professional software development practices.

## Features
- **Guided Workflow:** User-friendly wizard interface for step-by-step data processing.
- **Modular Architecture:** Strictly separated concerns (MVC-inspired) with distinct layers for UI, services, and configuration.
- **Data Integration:** Real-time data retrieval using public REST APIs.
- **Data Processing:** Automated cleaning and analysis using Pandas.

## Tech Stack
- **Language:** Python
- **GUI:** PySide6 (Qt for Python)
- **Data Analysis:** Pandas
- **API Handling:** Requests

## Getting Started
1. **Clone the repository.**
2. **Install dependencies:**
   ```bash
   pip install -r insightflow/requirements.txt
   ```
3. **Run the application:**
   ```bash
   python -m insightflow.main
   ```
