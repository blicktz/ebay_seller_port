# **Technical Document: Recreating the Listings Traffic Report via eBay API**

This document details how to replicate the "Listings Traffic Report" CSV using the **eBay Sell Analytics API**, the **Sell Inventory API**, and a local **SQLite database** for efficient data persistence and analysis.

## **1\. Core API Configuration**

To replicate the CSV's daily listing-level granularity, use these parameters:

* **Endpoint:** GET https://api.ebay.com/sell/analytics/v1/traffic\_report  
* **Dimension:** LISTING (One row per Item ID).  
* **Secondary Dimension:** DAY (Required for day-by-day rows).  
* **Filter:** date\_range:\[YYYYMMDD..YYYYMMDD\]  
* **Header:** X-EBAY-C-MARKETPLACE-ID: EBAY\_US (or your specific marketplace).

## **2\. Local Database Design (SQLite)**

Using a local database allows you to cache slow-moving metadata (Titles/Categories) and store historical traffic data for long-term trend analysis without hitting eBay rate limits.

### **Table: listings\_metadata**

Stores the static information about your items.

CREATE TABLE listings\_metadata (  
    item\_id TEXT PRIMARY KEY,  
    title TEXT,  
    category\_name TEXT,  
    start\_date TEXT,  
    last\_updated DATETIME DEFAULT CURRENT\_TIMESTAMP  
);

### **Table: daily\_traffic**

Stores the raw metrics returned by the Analytics API.

CREATE TABLE daily\_traffic (  
    item\_id TEXT,  
    report\_date TEXT, \-- Format: YYYY-MM-DD  
    total\_impressions INTEGER,  
    page\_views INTEGER,  
    transactions INTEGER,  
    ctr REAL,  
    conversion\_rate REAL,  
    search\_impressions INTEGER,  
    promoted\_search\_impressions INTEGER,  
    promoted\_non\_search\_impressions INTEGER,  
    organic\_non\_search\_impressions INTEGER,  
    PRIMARY KEY (item\_id, report\_date),  
    FOREIGN KEY (item\_id) REFERENCES listings\_metadata(item\_id)  
);

## **3\. Retrieving Listing Info (Metadata Sync)**

The Analytics API only returns numbers and IDs. You must sync listing info separately.

### **Step A: Sync Metadata**

* **API:** Sell Inventory API \-\> /inventory\_item (or Trading API GetSellerList).  
* **Logic:**  
  1. Fetch all active items.  
  2. Perform an INSERT OR REPLACE into the listings\_metadata table.  
  3. This only needs to run once a day or when you add new inventory.

## **4\. Complete Implementation Plan**

### **Phase 1: Authentication**

* Use a valid **Access Token** obtained from the eBay Developer Portal for the session.

### **Phase 2: Metadata Update (Local Cache)**

* Call getInventoryItems from the Inventory API.  
* Loop through the results and update the listings\_metadata SQLite table.

### **Phase 3: Traffic Data Ingestion**

1. **Download:** Call getTrafficReport for the desired window (e.g., last 3 days).  
2. **Upsert:** Insert the metrics into daily\_traffic. Use INSERT OR IGNORE or REPLACE to ensure you don't duplicate data for the same date.

### **Phase 4: Local Joining & Report Generation**

Instead of merging in Python memory, use a SQL query to generate your final report. This is much faster for large stores.

**SQL Query to Recreate CSV:**

SELECT   
    m.title AS "Listing title",  
    m.item\_id AS "eBay item ID",  
    m.category\_name AS "Category",  
    t.report\_date AS "Date",  
    t.total\_impressions AS "Total impressions",  
    t.page\_views AS "Total page views",  
    t.transactions AS "Quantity sold",  
    \-- Calculated Field: Organic Search Impressions  
    (t.search\_impressions \- t.promoted\_search\_impressions) AS "Organic Search Impressions",  
    \-- Calculated Field: % Top 20 Search  
    CASE WHEN t.total\_impressions \> 0   
         THEN (CAST(t.search\_impressions AS REAL) / t.total\_impressions) \* 100   
         ELSE 0 END AS "Search Share %"  
FROM daily\_traffic t  
JOIN listings\_metadata m ON t.item\_id \= m.item\_id  
WHERE t.report\_date BETWEEN '2026-02-01' AND '2026-02-25'  
ORDER BY t.report\_date DESC, t.item\_id;

## **5\. Summary of Best Practices**

* **Incremental Updates:** Only pull traffic data for the last 48 hours daily, as historical data doesn't change once finalized by eBay.  
* **Avoid "N+1" Queries:** Never call an API inside a loop for every row of your database. Fetch in bulk, store in SQLite, then query locally.  
* **Index for Speed:** Ensure item\_id and report\_date are indexed in SQLite to keep report generation instantaneous.

CREATE INDEX idx\_traffic\_date ON daily\_traffic(report\_date);

eof