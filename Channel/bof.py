import asyncio
import random
import pandas as pd

# Asynchronous version of BOF simulation
async def simulate_bof_response():
    # Load the dataset (consider loading this once and storing it)
    file_path = "Channel/BOF_DAS_Dataset.csv"
    df = pd.read_csv(file_path)
    
    # Random delay between 10 to 50 seconds
    delay = random.randint(10, 50)
    await asyncio.sleep(2)  # Non-blocking sleep
    
    # Randomly select a row
    random_row = df.sample(n=1).iloc[0]
    
    return random_row.to_dict()