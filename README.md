
# Informative Scenario Mining for Traffic Signal Control Evaluation

![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![Jupyter](https://img.shields.io/badge/Jupyter-F37626?style=flat-square&logo=jupyter&logoColor=white)
![SUMO](https://img.shields.io/badge/SUMO-0078D4?style=flat-square)
![TraCI](https://img.shields.io/badge/TraCI-555555?style=flat-square)

This research project explores methods for identifying informative traffic scenarios that reveal performance differences and weaknesses across traffic signal controllers. Using real-world traffic data and traffic simulation, the project aims to identify diagnostically valuable scenarios for more effective controller evaluation.

---

## Repository Structure

```text
informative-scenario-mining/
├── data/                         # Local traffic datasets (not tracked)
│   ├── raw/
│   └── processed/
├── notebooks/
│   ├── 01_traffic_data_eda.ipynb # Traffic data exploration
│   └── 02_sumo_quickstart.ipynb  # SUMO simulation testing
├── simulations/                  # SUMO networks and configurations
├── results/
│   ├── raw/                      # Raw simulation outputs (not tracked)
│   ├── figures/                  # Visualizations
│   └── summaries/                # Aggregated experiment results
├── environment.yml               # Conda environment specification
├── .gitignore
└── README.md
```