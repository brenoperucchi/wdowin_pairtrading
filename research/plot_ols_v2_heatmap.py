import sys
import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

def generate_heatmap():
    csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                            "data", "reports", "ols_v2", "phase_1_zscores", "ols_zscores_grid.csv")
    
    if not os.path.exists(csv_path):
        print(f"Error: Could not find {csv_path}")
        return
        
    df = pd.read_csv(csv_path)
    
    # Filter for the best Z_ATT (which was 1.0)
    df_att = df[df['Z_ATT'] == 1.0].copy()
    
    if df_att.empty:
        print("No data found for Z_ATT = 1.0")
        return
        
    # Pivot the data for Ret/DD
    pivot_retdd = df_att.pivot(index="Z_WDO", columns="Z_DI", values="Ret_DD")
    
    # Plotting
    plt.figure(figsize=(10, 8))
    sns.heatmap(pivot_retdd, annot=True, cmap="RdYlGn", fmt=".2f", linewidths=.5)
    plt.title("OLS V2: Heatmap Ret/DD (Z_WDO vs Z_DI) para Z_ATT = 1.0")
    plt.xlabel("Z_DI")
    plt.ylabel("Z_WDO")
    
    out_path = os.path.join(os.path.dirname(csv_path), "heatmap_ols_phase1.png")
    plt.savefig(out_path)
    print(f"Heatmap saved to {out_path}")

if __name__ == "__main__":
    generate_heatmap()
