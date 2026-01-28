import os

css = """
    /* ========== CPC Header Banner - Final Fix ========== */
    .cpc-header {
        position: relative;
        background: linear-gradient(90deg, #D32F2F 0%, #C62828 50%, #B71C1C 100%);
        padding: 40px 0;
        margin: -6rem -4rem 30px -4rem;
        box-shadow: 0 8px 24px rgba(0,0,0,0.5);
        overflow: visible;
        width: calc(100% + 8rem);
        display: flex;
        align-items: center;
        justify-content: center;
        flex-direction: row;
        gap: 30px;
    }
    
    .cpc-header::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: radial-gradient(circle at 50% 50%, rgba(255, 215, 0, 0.15) 0%, transparent 60%);
        pointer-events: none;
    }
    
    /* 3D Gold Emblem using CSS Text */
    .party-emblem-text {
        font-size: 140px;
        line-height: 1;
        font-family: sans-serif;
        cursor: default;
        
        /* Gold Gradient */
        background: linear-gradient(135deg, #FFF59D 0%, #FFD700 30%, #FF8F00 60%, #FFD700 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        color: transparent;
        
        /* Deep 3D Shadow/Glow */
        filter: drop-shadow(0 4px 0px #B8860B) drop-shadow(0 8px 10px rgba(0,0,0,0.6));
        
        flex-shrink: 0;
        margin-right: 20px;
        margin-left: 20px;
    }
    
    .cpc-header-title {
        font-family: "STFangsong", "FangSong", "Songti SC", "SimSun", serif;
        font-size: 5.5vw;
        font-weight: 900;
        margin: 0;
        letter-spacing: 0.05em;
        line-height: 1.1;
        white-space: nowrap;
        
        background: linear-gradient(180deg, #FFFFE0 0%, #FFD700 25%, #DAA520 50%, #FFD700 75%, #FFFFE0 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        
        filter: drop-shadow(0 3px 0px #8B0000) drop-shadow(0 6px 6px rgba(0,0,0,0.5));
    }
    
    .decorative-stars {
        position: absolute;
        width: 100%;
        height: 100%;
        top: 0;
        left: 0;
        pointer-events: none;
        z-index: 0;
    }
    
    .star {
        position: absolute;
        color: #FFD700;
        font-size: 24px;
        opacity: 0.6;
        animation: star-pulse 4s ease-in-out infinite;
        filter: drop-shadow(0 0 5px rgba(255, 215, 0, 0.8));
    }
    
    @keyframes star-pulse {
        0%, 100% { opacity: 0.4; transform: scale(1); }
        50% { opacity: 0.8; transform: scale(1.3); }
    }
    
    .star:nth-child(1) { top: 20%; left: 10%; font-size: 32px; animation-delay: 0s; }
    .star:nth-child(2) { top: 70%; left: 5%; font-size: 20px; animation-delay: 1s; }
    .star:nth-child(3) { top: 30%; right: 10%; font-size: 28px; animation-delay: 2s; }
    .star:nth-child(4) { top: 80%; right: 15%; font-size: 18px; animation-delay: 3s; }
"""

html = """
<!-- CPC Header Banner -->
<div class="cpc-header">
<div class="decorative-stars">
<div class="star">★</div>
<div class="star">★</div>
<div class="star">★</div>
<div class="star">★</div>
</div>
<!-- Unicode Emblem Styled with CSS -->
<div class="party-emblem-text">☭</div>
<h1 class="cpc-header-title">党政历史文献智能化处理</h1>
</div>
"""

try:
    with open('app.py', 'r') as f:
        lines = f.readlines()

    start_idx = -1
    end_idx = -1

    for i, line in enumerate(lines):
        if "/* ========== Import Chinese Fonts ========== */" in line:
            start_idx = i
        if '""", unsafe_allow_html=True)' in line and i > start_idx:
            end_idx = i
            break
            
    if start_idx != -1 and end_idx != -1:
        print(f"Replacing lines {start_idx} to {end_idx}")
        
        # Keep indentation of first line
        indent = lines[start_idx].split('/*')[0]
        
        new_block = f'''{indent}/* ========== Import Chinese Fonts ========== */
{indent}@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@900&family=Ma+Shan+Zheng&display=swap');
{indent}{css}
{indent}</style>
{indent}{html}
{indent}""", unsafe_allow_html=True)
'''
        
        # We need to construct the file content carefully
        # The new_block replaces everything from start_idx to end_idx (inclusive)
        
        with open('app.py', 'w') as f:
            f.writelines(lines[:start_idx])
            f.write(new_block)
            f.writelines(lines[end_idx+1:])
            
        print("Successfully patched app.py")
    else:
        print(f"Markers not found. Start: {start_idx}, End: {end_idx}")

except Exception as e:
    print(f"Error: {e}")
