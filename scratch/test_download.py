import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        print("Launching browser...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        
        url = "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/boletim-diario/boletim-diario-do-mercado/"
        print(f"Navigating to {url}...")
        await page.goto(url, wait_until="networkidle", timeout=30000)
        
        frame = page.frame(name="bvmf_iframe")
        if frame is None:
            print("Frame 'bvmf_iframe' not found!")
            await browser.close()
            return
            
        print("Clicking 'Derivativos' tab...")
        nav_derivativos = frame.locator('.nav-link:has-text("Derivativos")')
        await nav_derivativos.click()
        print("Clicked 'Derivativos' nav-link.")
        await page.wait_for_timeout(2000)
        
        # Click the dropdown option "Derivativos de bolsa"
        print("Clicking 'Derivativos de bolsa' item...")
        bolsa_item = frame.locator('a.dropdown-item:has-text("Derivativos de bolsa")')
        await bolsa_item.click()
        print("Clicked 'Derivativos de bolsa' link.")
        await page.wait_for_timeout(5000) # Wait for page contents to load
        
        # Take a screenshot to verify what it looks like now
        await page.screenshot(path="scratch/after_bolsa_click.png")
        print("Saved screenshot to scratch/after_bolsa_click.png")
        
        # Select 'OpenPositionsEquities@false' in the selectTabelas dropdown
        print("Selecting 'Posições em aberto' option...")
        await frame.select_option('#selectTabelas', 'OpenPositionsEquities@false')
        print("Selected 'OpenPositionsEquities@false'. Waiting for table to load...")
        await page.wait_for_timeout(8000) # Wait 8 seconds for the table to load!
        
        # Take a screenshot to verify what it looks like now
        await page.screenshot(path="scratch/after_table_select.png")
        print("Saved screenshot to scratch/after_table_select.png")
        
        # Let's search inside the DOM for text containing 'download' or 'csv', or find any links/buttons
        search_res = await frame.evaluate("""() => {
            const results = [];
            // Let's find all interactive/icon elements
            const elements = Array.from(document.querySelectorAll('a, button, i, svg, span'));
            
            elements.forEach((el, idx) => {
                const text = el.innerText || el.textContent || '';
                const html = el.outerHTML || '';
                const id = el.id || '';
                const cls = (typeof el.className === 'string') ? el.className : (el.className && el.className.baseVal) || '';
                
                const isMatch = html.toLowerCase().includes('download') || 
                                html.toLowerCase().includes('csv') || 
                                html.toLowerCase().includes('xls') || 
                                id.toLowerCase().includes('download') || 
                                cls.toLowerCase().includes('download') || 
                                cls.toLowerCase().includes('export') ||
                                cls.toLowerCase().includes('icon') ||
                                (el.tagName.toLowerCase() === 'svg');
                                
                if (isMatch) {
                    results.push({
                        idx,
                        tagName: el.tagName,
                        className: cls,
                        id: id,
                        text: text.trim().substring(0, 100),
                        outerHTML: html.substring(0, 200)
                    });
                }
            });
            return results;
        }""")
        
        print(f"\nFound {len(search_res)} potential download/export elements:")
        for idx, el in enumerate(search_res[:100]):
            print(f"Elem {idx}: Tag={el['tagName']}, Class='{el['className']}', ID='{el['id']}', Text='{el['text']}', HTML='{el['outerHTML']}'")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())

