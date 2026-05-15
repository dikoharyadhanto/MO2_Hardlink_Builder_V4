import json
import sys
from pathlib import Path
from datetime import datetime

class ReportGenerator:
    def __init__(self, manifest_path=None, report_path=None, output_html=None):
        if not manifest_path or not report_path or not output_html:
            raise ValueError("All paths (manifest, report, output_html) must be provided to ReportGenerator")

        self.manifest_path = Path(manifest_path)
        self.report_path = Path(report_path)
        self.output_html = Path(output_html)

    def generate(self, verification_results=None, show_deployment=True):
        execution = {}
        if show_deployment and self.report_path.exists():
            print(f">>> Reading execution report ({self.report_path.stat().st_size / 1024 / 1024:.2f} MB)...")
            with open(self.report_path, 'r') as f:
                execution = json.load(f)
        elif not verification_results:
            print(f"[!] Report generation skipped: No report file found and no verification results provided.")
            return

        now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        
        # Calculate statistics
        total = len(execution)
        success_list = []
        failed_list = []
        
        hardlinks = 0
        copies = 0
        
        print(">>> Processing statistics...")
        for target, data in execution.items():
            status = data.get('status', 'N/A')
            method = data.get('method', 'N/A')
            mod = data.get('mod', 'Unknown')
            
            # Map values to integers for compact storage
            # Status: 1 = SUCCESS, 0 = FAILED/Other
            s_int = 1 if "SUCCESS" in status else 0
            # Method: 0 = hardlink, 1 = copy, 2 = N/A
            m_int = 0 if method == 'hardlink' else (1 if method == 'copy' else 2)
            
            row = [target, s_int, m_int, mod, status] # Keeping original status string for display
            
            if s_int == 1:
                success_list.append(row)
                if m_int == 0: hardlinks += 1
                elif m_int == 1: copies += 1
            else:
                failed_list.append(row)

        total_success = len(success_list)
        total_failed = len(failed_list)

        # Merge for display: Failures first
        full_data = failed_list + success_list

        print(f">>> Building paginated HTML for {total} files...")

        html_chunks = []
        html_chunks.append(f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>MO2 Hardlink Builder Report</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #1a1a1a; color: #e0e0e0; margin: 20px; }}
        .container {{ max-width: 1200px; margin: auto; }}
        .header {{ background: #2d2d2d; padding: 20px; border-radius: 8px; border-left: 5px solid #4CAF50; margin-bottom: 20px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }}
        .stat-card {{ background: #2d2d2d; padding: 15px; border-radius: 8px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
        .stat-card h3 {{ margin: 0; font-size: 14px; color: #888; }}
        .stat-card p {{ margin: 10px 0 0; font-size: 24px; font-weight: bold; color: #4CAF50; }}
        .warning-box {{ background: #443300; padding: 15px; border-radius: 8px; border-left: 5px solid #ff9800; margin-bottom: 20px; font-size: 14px; }}
        .error-box {{ background: #441111; padding: 15px; border-radius: 8px; border-left: 5px solid #ff3333; margin-bottom: 20px; font-size: 14px; }}
        .success-box {{ background: #114411; padding: 15px; border-radius: 8px; border-left: 5px solid #4CAF50; margin-bottom: 20px; font-size: 14px; }}
        
        .nav-bar {{ display: flex; align-items: center; gap: 10px; margin-bottom: 15px; background: #2d2d2d; padding: 10px; border-radius: 8px; }}
        .pagination-info {{ flex-grow: 1; font-size: 14px; color: #aaa; }}
        .page-btn {{ background: #3d3d3d; color: #fff; border: 1px solid #444; padding: 5px 12px; border-radius: 4px; cursor: pointer; }}
        .page-btn:disabled {{ opacity: 0.3; cursor: not-allowed; }}
        .page-btn:hover:not(:disabled) {{ background: #555; }}
        .page-btn.active {{ background: #4CAF50; border-color: #4CAF50; }}

        .search-box {{ width: 100%; padding: 12px; margin-bottom: 15px; border-radius: 8px; border: 1px solid #444; background: #2d2d2d; color: #fff; box-sizing: border-box; }}
        
        table {{ width: 100%; border-collapse: collapse; background: #2d2d2d; border-radius: 8px; overflow: hidden; table-layout: fixed; }}
        th {{ background: #3d3d3d; color: #fff; text-align: left; padding: 12px; font-size: 14px; }}
        td {{ padding: 10px; border-bottom: 1px solid #3d3d3d; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        tr:hover {{ background: #353535; }}
        .status-success {{ color: #4CAF50; font-weight: bold; }}
        .status-failed {{ color: #f44336; font-weight: bold; }}
        .method-tag {{ background: #444; padding: 2px 8px; border-radius: 4px; font-size: 11px; }}

        .filter-btn {{
            background: #3d3d3d;
            border: 1px solid #444;
            color: #AAA;
            padding: 6px 15px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
        }}
        .filter-btn:hover {{ background: #444; color: #FFF; }}
        .filter-btn.active {{ background: #388E3C; color: #FFF; border-color: #4CAF50; font-weight: bold; }}
        #filter-failed.active {{ background: #D32F2F; border-color: #F44336; }}
        #filter-hardlink.active {{ background: #1976D2; border-color: #2196F3; }}
        #filter-copy.active {{ background: #7B1FA2; border-color: #9C27B0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>MO2 Hardlink Builder Report</h1>
            <p>Generated at: {now}</p>
        </div>

        <div class="stats-grid">
            <div class="stat-card"><h3>Total Files</h3><p>{total}</p></div>
            <div class="stat-card"><h3>Success</h3><p>{total_success}</p></div>
            <div class="stat-card"><h3>Hardlinks</h3><p>{hardlinks}</p></div>
            <div class="stat-card"><h3>Copies</h3><p>{copies}</p></div>
        </div>
""")

        # --- VERIFICATION SECTION ---
        if verification_results:
            missing = verification_results.get("missing_files", [])
            zeros = verification_results.get("zero_byte_files", [])
            configs = verification_results.get("config_mismatch", [])
            saves = verification_results.get("save_issues", [])
            quarantined = verification_results.get("quarantined_items", [])
            has_historic = verification_results.get("has_historic_quarantine", False)
            
            has_issues = any([missing, zeros, configs, saves])
            
            if has_issues:
                html_chunks.append('<div class="error-box"><h3>⚠️ Post-Deployment Verification Warnings</h3><ul>')
                
                if configs:
                    html_chunks.append(f"<li><strong>Config Mismatch:</strong> {len(configs)} issue(s) detected with INIs / Plugins / Load Order.</li>")
                    for c in configs: html_chunks.append(f"<li>&nbsp;&nbsp;&bull; {c}</li>")
                
                if missing:
                    html_chunks.append(f"<li><strong>Missing Files:</strong> {len(missing)} files from manifest are missing in Standalone folder.</li>")
                    for m in missing[:5]: html_chunks.append(f"<li>&nbsp;&nbsp;&bull; {m['file']} ({m['mod']})</li>")
                    if len(missing) > 5: html_chunks.append(f"<li>&nbsp;&nbsp;&bull; ... and {len(missing)-5} more.</li>")
                
                if zeros:
                    html_chunks.append(f"<li><strong>Zero-Byte Files:</strong> {len(zeros)} files have 0 bytes size.</li>")
                
                if saves:
                    for s in saves:
                        summary = s if isinstance(s, str) else s.get("summary", "Save sync issue")
                        files = [] if isinstance(s, str) else s.get("missing_files", [])
                        source = "Unknown" if isinstance(s, str) else s.get("source", "Source")
                        
                        html_chunks.append(f"<li><strong>Save Sync Issue:</strong> {summary} (Source: {source})</li>")
                        if files:
                            for f in files[:5]: html_chunks.append(f"<li>&nbsp;&nbsp;&bull; Missing: {f}</li>")
                            if len(files) > 5: html_chunks.append(f"<li>&nbsp;&nbsp;&bull; ... and {len(files)-5} more.</li>")

                html_chunks.append('</ul></div>')

            # --- LAUNCHER STATUS ---
            wrapper_info = verification_results.get("wrapper_info", {})
            if wrapper_info:
                w_type = wrapper_info.get("type", "N/A")
                if w_type == "EXE":
                    html_chunks.append(f"""
                        <div class="success-box" style="background: #114411; border-left: 5px solid #4CAF50;">
                            <h3>🚀 Launcher Status: Success (EXE Wrapper)</h3>
                            <p>All loaders and launchers have been successfully hijacked with professional EXE wrappers. Isolation is fully active.</p>
                        </div>
                    """)
                else:
                    html_chunks.append(f"""
                        <div class="warning-box" style="background: #442200; border-left: 5px solid #ff9800;">
                            <h3>⚠️ Launcher Status: Fallback (.BAT Mode)</h3>
                            <p>EXE wrappers could not be compiled. Use the generated <code>.bat</code> files to launch.</p>
                        </div>
                    """)

            # --- QUARANTINE SECTION ---
            if quarantined or has_historic:
                html_chunks.append('<div class="warning-box" style="background: #1a3a5a; border-left: 5px solid #3498db;"><h3>ℹ️ Manual Action Required: Quarantined Saves</h3><ul>')
                if quarantined:
                    for q in quarantined:
                        html_chunks.append(f"<li>&nbsp;&nbsp;&bull; <strong>{q['file']}</strong> (Reason: {q['reason']})</li>")
                if has_historic:
                    html_chunks.append('<li style="margin-top: 15px; color: #ffeb3b;"><strong>ℹ️ Notice:</strong> You have previous backups in history.</li>')
                html_chunks.append('</ul></div>')

            # --- MOD AUDIT SECTION ---
            mod_audit = verification_results.get("mod_audit", {})
            redundant_mods = mod_audit.get("redundant_mods", [])
            untracked_mods = mod_audit.get("untracked_mods", [])
            broken_mods = mod_audit.get("broken_mods", [])
            
            if redundant_mods or untracked_mods or broken_mods:
                html_chunks.append('<div class="header" style="background: #2d2d2d; border-left: 5px solid #9b59b6; margin-top: 20px;"><h3>📊 Build Integrity Audit: Mod Analysis</h3>')
                html_chunks.append('<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px; margin-top: 15px;">')
                
                if redundant_mods:
                    html_chunks.append(f"""
                        <div style="background: #444411; padding: 15px; border-radius: 8px; border-top: 3px solid #ffeb3b;">
                            <strong style="color: #ffeb3b;">📎 Redundant Mods ({len(redundant_mods)})</strong><br>
                            <small style="color: #aaa; font-style: italic;">Note: These mods contain no game files (e.g. only Readmes or Separators) and are safe to skip.</small>
                            <ul style="margin: 10px 0 0 15px; padding: 0; font-size: 11px;">
                                {''.join([f"<li>{m}</li>" for m in redundant_mods[:5]])}
                                {f'<li>... and {len(redundant_mods)-5} more.</li>' if len(redundant_mods) > 5 else ''}
                            </ul>
                        </div>
                    """)

                if untracked_mods:
                    html_chunks.append(f"""
                        <div style="background: #1a3a5a; padding: 15px; border-radius: 8px; border-top: 3px solid #3498db;">
                            <strong style="color: #3498db;">👻 Ghost Mods ({len(untracked_mods)})</strong><br>
                            <ul style="margin: 10px 0 0 15px; padding: 0; font-size: 11px;">
                                {''.join([f"<li>{m}</li>" for m in list(untracked_mods)[:5]])}
                                {f'<li>... and {len(untracked_mods)-5} more.</li>' if len(untracked_mods) > 5 else ''}
                            </ul>
                        </div>
                    """)

                if broken_mods:
                    html_chunks.append(f"""
                        <div style="background: #441111; padding: 15px; border-radius: 8px; border-top: 3px solid #ff3333;">
                            <strong style="color: #ff3333;">❌ Broken Mods ({len(broken_mods)})</strong><br>
                            <small style="color: #ff9999; font-style: italic;">Technical errors detected! See <b>brokenmods_logs.txt</b> in the output folder for details.</small>
                            <ul style="margin: 10px 0 0 15px; padding: 0; font-size: 11px;">
                                {''.join([f"<li>{m['name']} ({m['rate']}) - {m.get('reason', 'Unknown Issue')}</li>" for m in broken_mods[:5]])}
                                {f'<li>... and {len(broken_mods)-5} more.</li>' if len(broken_mods) > 5 else ''}
                            </ul>
                        </div>
                    """)
                html_chunks.append('</div></div>')

        if show_deployment:
            html_chunks.append("""
        <input type="text" id="searchInput" class="search-box" placeholder="Search current page (name or mod)...">
        
        <div class="filter-bar" style="display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap;">
            <button class="filter-btn active" id="filter-all" onclick="applyFilter('all')">All Files</button>
            <button class="filter-btn" id="filter-success" onclick="applyFilter('success')">Success</button>
            <button class="filter-btn" id="filter-failed" onclick="applyFilter('failed')">Failed</button>
            <button class="filter-btn" id="filter-hardlink" onclick="applyFilter('hardlink')">Hardlinks</button>
            <button class="filter-btn" id="filter-copy" onclick="applyFilter('copy')">Copies</button>
        </div>
        
        <div class="nav-bar">
            <div class="pagination-info" id="pageInfo">Showing 0-0 of 0</div>
            <button class="page-btn" onclick="goToPage(0)">First</button>
            <button class="page-btn" id="prevBtn" onclick="changePage(-1)">Prev</button>
            <div id="pageNumbers" style="display: flex; gap: 5px;"></div>
            <button class="page-btn" id="nextBtn" onclick="changePage(1)">Next</button>
            <button class="page-btn" onclick="goToPage(totalPages - 1)">Last</button>
        </div>

        <table id="reportTable">
            <thead>
                <tr>
                    <th style="width: 50%;">Target File</th>
                    <th style="width: 25%;">Source Mod</th>
                    <th style="width: 15%;">Status</th>
                    <th style="width: 10%;">Method</th>
                </tr>
            </thead>
            <tbody id="tableBody"></tbody>
        </table>
    </div>

    <script>
        // Compact Data: [target, s_int, m_int, mod, status_str]
        const DATA = """)
            # Use json.dumps for the large data array
            html_chunks.append(json.dumps(full_data))
            html_chunks.append(""";
        
        const PAGE_SIZE = 5000;
        let currentPage = 0;
        let currentFilter = 'all';
        let filteredData = DATA;
        
        const methodMap = {0: 'hardlink', 1: 'copy', 2: 'N/A'};

        function applyFilter(filterType) {
            currentFilter = filterType;
            currentPage = 0;
            
            // Update button styles
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById(`filter-${filterType}`).classList.add('active');

            if (filterType === 'all') {
                filteredData = DATA;
            } else if (filterType === 'success') {
                filteredData = DATA.filter(row => row[1] === 1);
            } else if (filterType === 'failed') {
                filteredData = DATA.filter(row => row[1] === 0);
            } else if (filterType === 'hardlink') {
                filteredData = DATA.filter(row => row[2] === 0);
            } else if (filterType === 'copy') {
                filteredData = DATA.filter(row => row[2] === 1);
            }
            
            renderTable();
        }

        function renderPagination() {
            const totalRows = filteredData.length;
            const totalPages = Math.ceil(totalRows / PAGE_SIZE);
            const pageNumbers = document.getElementById('pageNumbers');
            const maxButtons = 10;
            let startPage = Math.max(0, currentPage - Math.floor(maxButtons / 2));
            let endPage = Math.min(totalPages, startPage + maxButtons);
            
            if (endPage - startPage < maxButtons) {
                startPage = Math.max(0, endPage - maxButtons);
            }

            let html = '';
            for (let i = startPage; i < endPage; i++) {
                const activeClass = i === currentPage ? 'active' : '';
                html += `<button class="page-btn ${activeClass}" onclick="goToPage(${i})">${i + 1}</button>`;
            }
            pageNumbers.innerHTML = html;

            document.getElementById('prevBtn').disabled = (currentPage === 0);
            document.getElementById('nextBtn').disabled = (currentPage >= totalPages - 1 || totalPages <= 1);
        }

        function renderTable() {
            const totalRows = filteredData.length;
            const totalPages = Math.ceil(totalRows / PAGE_SIZE);
            const start = currentPage * PAGE_SIZE;
            const end = Math.min(start + PAGE_SIZE, totalRows);
            const tableBody = document.getElementById('tableBody');
            const pageInfo = document.getElementById('pageInfo');
            
            let html = '';
            for (let i = start; i < end; i++) {
                const [target, s_int, m_int, mod, status] = filteredData[i];
                const statusClass = s_int === 1 ? 'status-success' : 'status-failed';
                const methodName = methodMap[m_int];
                
                html += `
                    <tr>
                        <td title="${target}">${target}</td>
                        <td title="${mod}">${mod}</td>
                        <td class="${statusClass}">${status}</td>
                        <td><span class="method-tag">${methodName}</span></td>
                    </tr>
                `;
            }
            
            tableBody.innerHTML = html;
            pageInfo.textContent = `Showing ${totalRows === 0 ? 0 : start + 1}-${end} of ${totalRows} (Page ${totalPages === 0 ? 0 : currentPage + 1}/${totalPages})`;
            
            renderPagination();
        }

        function changePage(delta) {
            const totalRows = filteredData.length;
            const totalPages = Math.ceil(totalRows / PAGE_SIZE);
            currentPage = Math.min(Math.max(0, currentPage + delta), Math.max(0, totalPages - 1));
            renderTable();
            document.getElementById('searchInput').value = '';
        }

        function goToPage(page) {
            const totalRows = filteredData.length;
            const totalPages = Math.ceil(totalRows / PAGE_SIZE);
            currentPage = Math.min(Math.max(0, page), Math.max(0, totalPages - 1));
            renderTable();
            document.getElementById('searchInput').value = '';
        }

        // Local Search: Only filters current view
        document.getElementById('searchInput').addEventListener('keyup', function() {
            const search = this.value.toLowerCase();
            const rows = document.querySelectorAll('#tableBody tr');
            
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(search) ? '' : 'none';
            });
        });

        // Initial Render
        renderTable();
    </script>
</body>
</html>
""")

        with open(self.output_html, 'w', encoding='utf-8') as f:
            f.write("".join(html_chunks))
        print(f"[SUCCESS] Interactive report generated at: {self.output_html}")

