import time
import random
import pandas as pd

# Load the dataset
file_path = "BOF_DAS_Dataset.csv"
df = pd.read_csv(file_path)

def simulate_bof_response(df):
    # Random delay between 10 to 60 seconds
    delay = random.randint(10, 50)
    time.sleep(delay)
    
    # Randomly select a row
    random_row = df.sample(n=1).iloc[0]
    
    return random_row.to_dict()

# Simulate BOF response
while True:
    print(simulate_bof_response(df))
