(function installConciergeTheme(global) {
  const DEFAULTS = Object.freeze({
    background: "#FAF8F3",
    surface: "#FFFEFB",
    surfaceElevated: "#FFFFFF",
    surfaceSubtle: "#F1EEE6",
    headingColor: "#1D1C1A",
    bodyColor: "#1D1C1A",
    textSecondary: "#625D55",
    accent: "#B99A70",
    accentForeground: "#1D1C1A",
    primaryColor: "#1D1C1A",
    secondaryColor: "#39342F",
    buttonText: "#FFFFFF",
    secondaryButtonText: "#FFFFFF",
    composerBackground: "#FFFFFF",
    border: "#D8D0C4",
    hoverColor: "#121211",
    secondaryHoverColor: "#292520",
    focusColor: "#1D1C1A",
    iconColor: "#1D1C1A",
    navBackground: "#FFFEFB",
    navText: "#1D1C1A",
    navActiveBackground: "#EDE5D8",
    navActiveText: "#1D1C1A",
    menuBackground: "#FFFFFF",
    cardBackground: "#FFFEFB",
    inputBackground: "#FFFFFF",
    inputText: "#1D1C1A",
    inputPlaceholder: "#625D55",
    inputBorder: "#D8D0C4",
    userMessageBackground: "#EDE5D8",
    userMessageText: "#1D1C1A",
    assistantMessageBackground: "#FFFFFF",
    assistantMessageText: "#1D1C1A",
    notificationSuccess: "#245D42",
    notificationSuccessBackground: "#EAF3ED",
    notificationWarning: "#624819",
    notificationWarningBackground: "#F7F0DF",
    notificationError: "#842F35",
    notificationErrorBackground: "#FAECEC",
    notificationInfo: "#254B69",
    notificationInfoBackground: "#EAF1F7",
    fontFamily: "Inter",
    headingFontFamily: "Playfair Display",
    radius: 12,
    shadow: "subtle",
    density: "comfortable",
    baseFontSize: 15,
  });

  const STATUS_TOKENS = Object.freeze({
    notificationSuccess: "#245D42",
    notificationSuccessBackground: "#EAF3ED",
    notificationWarning: "#624819",
    notificationWarningBackground: "#F7F0DF",
    notificationError: "#842F35",
    notificationErrorBackground: "#FAECEC",
    notificationInfo: "#254B69",
    notificationInfoBackground: "#EAF1F7",
  });

  function definePalette({
    id, name, description, background, primaryColor, secondaryColor, accent, bodyColor,
    surface, surfaceElevated, surfaceSubtle, textSecondary, border, userMessageBackground,
    navActiveBackground, inputPlaceholder, secondaryButtonText = "#FFFFFF",
    hoverColor, secondaryHoverColor, fontFamily = "Inter", headingFontFamily = "Playfair Display",
    radius = 12,
  }) {
    return Object.freeze({
      id,
      name,
      description,
      swatches: Object.freeze([background, primaryColor, secondaryColor, accent, bodyColor]),
      background,
      surface,
      surfaceElevated,
      surfaceSubtle,
      headingColor: primaryColor,
      bodyColor,
      textSecondary,
      accent,
      accentForeground: bodyColor,
      primaryColor,
      secondaryColor,
      buttonText: "#FFFFFF",
      secondaryButtonText,
      composerBackground: surfaceElevated,
      border,
      hoverColor,
      secondaryHoverColor,
      focusColor: primaryColor,
      iconColor: primaryColor,
      navBackground: surface,
      navText: bodyColor,
      navActiveBackground,
      navActiveText: primaryColor,
      menuBackground: surfaceElevated,
      cardBackground: surface,
      inputBackground: surfaceElevated,
      inputText: bodyColor,
      inputPlaceholder: inputPlaceholder || textSecondary,
      inputBorder: border,
      userMessageBackground,
      userMessageText: bodyColor,
      assistantMessageBackground: surfaceElevated,
      assistantMessageText: bodyColor,
      ...STATUS_TOKENS,
      fontFamily,
      headingFontFamily,
      radius,
      shadow: "subtle",
      density: "comfortable",
      baseFontSize: 15,
      contentWidth: 840,
      messageWidth: 680,
      composerWidth: 820,
      messageSpacing: 24,
    });
  }

  const PRESETS = Object.freeze({
    "royal-emerald-gold": definePalette({
      id: "royal-emerald-gold",
      name: "Royal Emerald & Gold",
      description: "Deep emerald, quiet gold, and warm ivory for a classic luxury welcome.",
      background: "#F7F3E9",
      primaryColor: "#102F29",
      secondaryColor: "#1D5145",
      accent: "#C5A46D",
      bodyColor: "#263D37",
      surface: "#FFFDF8",
      surfaceElevated: "#FFFFFF",
      surfaceSubtle: "#EEEAE0",
      textSecondary: "#52645E",
      border: "#D8D1C2",
      userMessageBackground: "#E8EFEA",
      navActiveBackground: "#E4EDE7",
      inputPlaceholder: "#596C64",
      hoverColor: "#0B241F",
      secondaryHoverColor: "#163F36",
      headingFontFamily: "Playfair Display",
    }),
    "midnight-sapphire": definePalette({
      id: "midnight-sapphire",
      name: "Midnight Sapphire",
      description: "A tailored navy foundation with restrained champagne accents and crisp surfaces.",
      background: "#EDF2F8",
      primaryColor: "#101C32",
      secondaryColor: "#20375A",
      accent: "#D7B98B",
      bodyColor: "#101C32",
      surface: "#F9FBFE",
      surfaceElevated: "#FFFFFF",
      surfaceSubtle: "#E4EAF2",
      textSecondary: "#46566D",
      border: "#CDD6E2",
      userMessageBackground: "#E3EAF3",
      navActiveBackground: "#E2EAF4",
      inputPlaceholder: "#52637A",
      hoverColor: "#0A1324",
      secondaryHoverColor: "#182B48",
      headingFontFamily: "Manrope",
    }),
    "champagne-onyx": definePalette({
      id: "champagne-onyx",
      name: "Champagne & Onyx",
      description: "Soft champagne neutrals, onyx typography, and a discreet brushed-brass note.",
      background: "#F5F0E7",
      primaryColor: "#1D1C1A",
      secondaryColor: "#39342F",
      accent: "#B99A70",
      bodyColor: "#1D1C1A",
      surface: "#FFFDFA",
      surfaceElevated: "#FFFFFF",
      surfaceSubtle: "#EDE6DB",
      textSecondary: "#625D55",
      border: "#D8D0C4",
      userMessageBackground: "#EEE7DC",
      navActiveBackground: "#ECE5D9",
      inputPlaceholder: "#6C665D",
      hoverColor: "#121211",
      secondaryHoverColor: "#292520",
      headingFontFamily: "Playfair Display",
    }),
    "pearl-sage": definePalette({
      id: "pearl-sage",
      name: "Pearl & Sage",
      description: "Pearl-white surfaces, garden sage, and a natural sand accent for a calm stay.",
      background: "#FAF8F3",
      primaryColor: "#29483C",
      secondaryColor: "#779487",
      accent: "#D4B99B",
      bodyColor: "#29483C",
      surface: "#FFFEFB",
      surfaceElevated: "#FFFFFF",
      surfaceSubtle: "#EDF1EA",
      textSecondary: "#526B60",
      border: "#D8DED5",
      userMessageBackground: "#E9EFE9",
      navActiveBackground: "#E5EDE6",
      inputPlaceholder: "#5E7368",
      secondaryButtonText: "#14221B",
      hoverColor: "#1E382E",
      secondaryHoverColor: "#8BA99A",
      headingFontFamily: "Playfair Display",
    }),
    "obsidian-copper": definePalette({
      id: "obsidian-copper",
      name: "Obsidian & Copper",
      description: "Architectural charcoal with earthy copper details and soft mineral neutrals.",
      background: "#F3F0EA",
      primaryColor: "#16191D",
      secondaryColor: "#2A3037",
      accent: "#BA805D",
      bodyColor: "#16191D",
      surface: "#FCFBF8",
      surfaceElevated: "#FFFFFF",
      surfaceSubtle: "#E8E5DF",
      textSecondary: "#555B61",
      border: "#D4D1CB",
      userMessageBackground: "#E9E6E0",
      navActiveBackground: "#E7E4DE",
      inputPlaceholder: "#5F646A",
      hoverColor: "#0B0D10",
      secondaryHoverColor: "#20252B",
      headingFontFamily: "Manrope",
    }),
  });

  // Legacy entries keep existing saved property designs rendering as authored.
  const LEGACY_PRESETS = Object.freeze({
    elegant: { background: "#f5f5f5", surface: "#ffffff", headingColor: "#202020", bodyColor: "#202020", textSecondary: "#666666", accent: "#444444", primaryColor: "#202020", secondaryColor: "#eeeeee", buttonText: "#ffffff", border: "#dedede", userMessageBackground: "#ededed", fontFamily: "Playfair Display", headingFontFamily: "Playfair Display", radius: 8, shadow: "subtle" },
    minimal: { background: "#f7f7f7", surface: "#ffffff", headingColor: "#171717", bodyColor: "#171717", textSecondary: "#686868", accent: "#111111", primaryColor: "#111111", secondaryColor: "#eeeeee", buttonText: "#ffffff", border: "#e2e2e2", userMessageBackground: "#eeeeee", fontFamily: "Inter", headingFontFamily: "Inter", radius: 8, shadow: "subtle" },
    "soft-gray": { background: "#f1f1f1", surface: "#ffffff", headingColor: "#222222", bodyColor: "#222222", textSecondary: "#6b6b6b", accent: "#444444", primaryColor: "#222222", secondaryColor: "#e8e8e8", buttonText: "#ffffff", border: "#dddddd", userMessageBackground: "#e8e8e8", fontFamily: "Geist", headingFontFamily: "Inter", radius: 12, shadow: "subtle" },
    "high-contrast": { background: "#ececec", surface: "#ffffff", headingColor: "#111111", bodyColor: "#111111", textSecondary: "#4d4d4d", accent: "#111111", primaryColor: "#111111", secondaryColor: "#e1e1e1", buttonText: "#ffffff", border: "#b8b8b8", userMessageBackground: "#e1e1e1", fontFamily: "Inter", headingFontFamily: "Inter", radius: 5, shadow: "none" },
    graphite: { background: "#202020", surface: "#292929", headingColor: "#f4f4f4", bodyColor: "#f4f4f4", textSecondary: "#b5b5b5", accent: "#f1f1f1", primaryColor: "#f1f1f1", secondaryColor: "#3b3b3b", buttonText: "#171717", border: "#454545", userMessageBackground: "#3b3b3b", userMessageText: "#f4f4f4", fontFamily: "Inter", headingFontFamily: "Inter", radius: 8, shadow: "subtle" },
    ocean: { background: "#edf5f6", surface: "#ffffff", headingColor: "#183039", bodyColor: "#183039", textSecondary: "#566b70", accent: "#287987", primaryColor: "#236a78", secondaryColor: "#dcecef", buttonText: "#ffffff", border: "#c8dfe2", userMessageBackground: "#dcecef", fontFamily: "Geist", headingFontFamily: "Inter", radius: 8, shadow: "subtle" },
    botanical: { background: "#f1f5f1", surface: "#ffffff", headingColor: "#20302a", bodyColor: "#20302a", textSecondary: "#5e6f64", accent: "#4b7659", primaryColor: "#3a6248", secondaryColor: "#e0eae2", buttonText: "#ffffff", border: "#cfddd1", userMessageBackground: "#e0eae2", fontFamily: "Geist", headingFontFamily: "Inter", radius: 8, shadow: "subtle" },
    rose: { background: "#f7f1f4", surface: "#ffffff", headingColor: "#322730", bodyColor: "#322730", textSecondary: "#74636d", accent: "#98677f", primaryColor: "#83556c", secondaryColor: "#efe1e9", buttonText: "#ffffff", border: "#e4d4dc", userMessageBackground: "#efe1e9", fontFamily: "Inter", headingFontFamily: "Inter", radius: 8, shadow: "subtle" },
    coral: { background: "#f8f1ef", surface: "#ffffff", headingColor: "#332723", bodyColor: "#332723", textSecondary: "#76625c", accent: "#ad5d4d", primaryColor: "#994d3e", secondaryColor: "#f2dfda", buttonText: "#ffffff", border: "#e5d2cc", userMessageBackground: "#f2dfda", fontFamily: "Inter", headingFontFamily: "Inter", radius: 8, shadow: "subtle" },
    "modern-elegance": { background: "#f5f4f0", surface: "#ffffff", headingColor: "#262a27", bodyColor: "#262a27", textSecondary: "#686c68", accent: "#78633c", primaryColor: "#304239", secondaryColor: "#ece9e1", buttonText: "#ffffff", border: "#dedbd2", userMessageBackground: "#ece9e1", fontFamily: "Playfair Display", headingFontFamily: "Playfair Display", radius: 8, shadow: "subtle" },
  });

  const TEMPLATE_PALETTES = Object.freeze({
    luxury: "royal-emerald-gold",
    elegant: "champagne-onyx",
    minimal: "champagne-onyx",
    business: "midnight-sapphire",
    resort: "pearl-sage",
    restaurant: "obsidian-copper",
    blank: "champagne-onyx",
  });

  const isColor = (value) => typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value);
  const fontNames = new Set(["Geist", "Inter", "Manrope", "DM Sans", "Poppins", "Montserrat", "Lato", "Merriweather", "Playfair Display", "system-ui"]);

  function luminance(value) {
    const channels = [1, 3, 5].map((offset) => parseInt(value.slice(offset, offset + 2), 16) / 255).map((channel) => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
  }

  function contrastRatio(first, second) {
    const [lighter, darker] = [luminance(first), luminance(second)].sort((a, b) => b - a);
    return (lighter + 0.05) / (darker + 0.05);
  }

  function readableForeground(preferred, background) {
    if (isColor(preferred) && contrastRatio(preferred, background) >= 4.5) return preferred;
    return contrastRatio("#FFFFFF", background) >= contrastRatio("#16191D", background) ? "#FFFFFF" : "#16191D";
  }

  const CHAT_PRESETS = Object.freeze({
    luxury: Object.freeze({
      id: "luxury", name: "Luxury Chat", description: "Deep emerald, warm ivory, and a restrained brass note for a gracious hotel welcome.",
      swatches: Object.freeze(["#F7F3E9", "#102F29", "#1D5145", "#E8EFEA", "#C5A46D"]), headerDesign: "solid", radius: 18, shadow: "strong",
      tokens: Object.freeze({ background: "#F7F3E9", surface: "#FFFDF8", headerBackground: "#102F29", headerText: "#FFFFFF", launcherBackground: "#102F29", launcherText: "#FFFFFF", guestBubbleBackground: "#102F29", guestBubbleText: "#FFFFFF", assistantBubbleBackground: "#FFFDF8", assistantBubbleText: "#263D37", inputBackground: "#FFFFFF", inputText: "#263D37", inputBorder: "#D8D1C2", sendBackground: "#102F29", sendText: "#FFFFFF", focusColor: "#102F29" }),
    }),
    chatgpt: Object.freeze({
      id: "chatgpt", name: "ChatGPT Inspired", description: "A quiet, spacious conversation with clean surfaces and direct typography.",
      swatches: Object.freeze(["#FFFFFF", "#202123", "#F4F4F4", "#FFFFFF", "#10A37F"]), headerDesign: "minimal", radius: 14, shadow: "subtle",
      tokens: Object.freeze({ background: "#FFFFFF", surface: "#FFFFFF", headerBackground: "#FFFFFF", headerText: "#202123", launcherBackground: "#202123", launcherText: "#FFFFFF", guestBubbleBackground: "#F4F4F4", guestBubbleText: "#202123", assistantBubbleBackground: "#FFFFFF", assistantBubbleText: "#202123", inputBackground: "#FFFFFF", inputText: "#202123", inputBorder: "#D9D9E3", sendBackground: "#202123", sendText: "#FFFFFF", focusColor: "#0B6E58" }),
    }),
    boutique: Object.freeze({
      id: "boutique", name: "Boutique Chat", description: "Personal, soft-edged surfaces with garden green and natural linen.",
      swatches: Object.freeze(["#FAF8F3", "#29483C", "#779487", "#E9EFE9", "#D4B99B"]), headerDesign: "soft", radius: 22, shadow: "subtle",
      tokens: Object.freeze({ background: "#FAF8F3", surface: "#FFFEFB", headerBackground: "#E9EFE9", headerText: "#29483C", launcherBackground: "#29483C", launcherText: "#FFFFFF", guestBubbleBackground: "#29483C", guestBubbleText: "#FFFFFF", assistantBubbleBackground: "#EDF1EA", assistantBubbleText: "#29483C", inputBackground: "#FFFFFF", inputText: "#29483C", inputBorder: "#D8DED5", sendBackground: "#29483C", sendText: "#FFFFFF", focusColor: "#29483C" }),
    }),
    midnight: Object.freeze({
      id: "midnight", name: "Midnight Chat", description: "An intimate dark interface with mineral charcoal and champagne highlights.",
      swatches: Object.freeze(["#16191D", "#101316", "#303944", "#242B32", "#D7B98B"]), headerDesign: "solid", radius: 18, shadow: "strong",
      tokens: Object.freeze({ background: "#16191D", surface: "#20262C", headerBackground: "#101316", headerText: "#F3F0EA", launcherBackground: "#D7B98B", launcherText: "#1D1C1A", guestBubbleBackground: "#303944", guestBubbleText: "#F6F5F2", assistantBubbleBackground: "#242B32", assistantBubbleText: "#F3F0EA", inputBackground: "#1E242A", inputText: "#F3F0EA", inputBorder: "#48515B", sendBackground: "#D7B98B", sendText: "#1D1C1A", focusColor: "#D7B98B" }),
    }),
  });
  const CHAT_TOKEN_FIELDS = Object.freeze(["background", "surface", "headerBackground", "headerText", "launcherBackground", "launcherText", "guestBubbleBackground", "guestBubbleText", "assistantBubbleBackground", "assistantBubbleText", "inputBackground", "inputText", "inputBorder", "sendBackground", "sendText", "focusColor"]);

  function normalizeChatConfig(design = {}) {
    const source = design.chat || {};
    const presetId = CHAT_PRESETS[source.presetId] ? source.presetId : "luxury";
    const defaults = CHAT_PRESETS[presetId];
    const paletteId = CHAT_PRESETS[source.paletteId] ? source.paletteId : presetId;
    const rawTokens = source.tokens && typeof source.tokens === "object" ? source.tokens : {};
    const chat = {
      presetId,
      paletteId,
      inheritLandingTheme: source.inheritLandingTheme !== false,
      displayMode: ["floating", "fullscreen", "embedded"].includes(source.displayMode) ? source.displayMode : "embedded",
      headerDesign: ["solid", "soft", "minimal"].includes(source.headerDesign) ? source.headerDesign : defaults.headerDesign,
      launcherIcon: ["concierge", "message", "sparkle"].includes(source.launcherIcon) ? source.launcherIcon : "concierge",
      sendButtonIcon: ["send", "arrow"].includes(source.sendButtonIcon) ? source.sendButtonIcon : "send",
      assistantName: String(source.assistantName || "Concierge").trim().slice(0, 60) || "Concierge",
      avatarUrl: typeof source.avatarUrl === "string" ? source.avatarUrl : "",
      welcomeMessage: String(source.welcomeMessage || "").trim().slice(0, 240),
      suggestedPrompts: Array.isArray(source.suggestedPrompts) ? source.suggestedPrompts.map((item) => String(item || "").trim().slice(0, 80)).filter(Boolean).slice(0, 4) : [],
      showTimestamps: source.showTimestamps === true,
      showTypingIndicator: source.showTypingIndicator !== false,
      showMinimizeControl: source.showMinimizeControl !== false,
      showExpandControl: source.showExpandControl !== false,
      allowFullscreenToggle: source.allowFullscreenToggle !== false,
      position: source.position === "bottom-left" ? "bottom-left" : "bottom-right",
      width: Number.isFinite(Number(source.width)) ? Math.max(320, Math.min(560, Number(source.width))) : 420,
      height: Number.isFinite(Number(source.height)) ? Math.max(360, Math.min(900, Number(source.height))) : 620,
      radius: Number.isFinite(Number(source.radius)) ? Math.max(8, Math.min(32, Number(source.radius))) : defaults.radius,
      shadow: ["none", "subtle", "strong"].includes(source.shadow) ? source.shadow : defaults.shadow,
      tokens: Object.fromEntries(CHAT_TOKEN_FIELDS.filter((key) => isColor(rawTokens[key])).map((key) => [key, rawTokens[key]])),
    };
    return { ...chat, defaults };
  }

  function resolveChatTokens(design = {}) {
    const chat = normalizeChatConfig(design);
    const landing = normalize(design);
    const presetTokens = chat.defaults.tokens;
    let tokens;
    if (chat.inheritLandingTheme) {
      tokens = {
        background: landing.background,
        surface: landing.surfaceElevated,
        headerBackground: chat.headerDesign === "solid" ? landing.primaryColor : chat.headerDesign === "soft" ? landing.surfaceSubtle : landing.surface,
        headerText: chat.headerDesign === "solid" ? landing.buttonText : landing.bodyColor,
        launcherBackground: landing.primaryColor,
        launcherText: landing.buttonText,
        guestBubbleBackground: landing.userMessageBackground,
        guestBubbleText: landing.userMessageText,
        assistantBubbleBackground: landing.assistantMessageBackground,
        assistantBubbleText: landing.assistantMessageText,
        inputBackground: landing.inputBackground,
        inputText: landing.inputText,
        inputBorder: landing.inputBorder,
        sendBackground: landing.primaryColor,
        sendText: landing.buttonText,
        focusColor: landing.focusColor,
      };
    } else {
      tokens = { ...(CHAT_PRESETS[chat.paletteId]?.tokens || presetTokens), ...chat.tokens };
      if (chat.headerDesign === "soft") { tokens.headerBackground = tokens.surface; tokens.headerText = tokens.assistantBubbleText; }
      if (chat.headerDesign === "minimal") { tokens.headerBackground = tokens.background; tokens.headerText = tokens.assistantBubbleText; }
    }
    for (const field of ["guestBubbleText", "assistantBubbleText", "headerText", "launcherText", "sendText"]) {
      const backgroundField = ({ guestBubbleText: "guestBubbleBackground", assistantBubbleText: "assistantBubbleBackground", headerText: "headerBackground", launcherText: "launcherBackground", sendText: "sendBackground" })[field];
      if (contrastRatio(tokens[field], tokens[backgroundField]) < 4.5) tokens[field] = readableForeground(tokens[field], tokens[backgroundField]);
    }
    return { ...tokens, shadow: chat.shadow === "none" ? "none" : chat.shadow === "strong" ? "0 20px 56px rgba(15, 23, 42, .2)" : "0 8px 28px rgba(15, 23, 42, .11)" };
  }

  function applyChat(root, design = {}) {
    const chat = normalizeChatConfig(design);
    const tokens = resolveChatTokens(design);
    const variables = {
      "--chat-window-bg": tokens.background,
      "--chat-surface": tokens.surface,
      "--chat-header-bg": tokens.headerBackground,
      "--chat-header-text": tokens.headerText,
      "--chat-launcher-bg": tokens.launcherBackground,
      "--chat-launcher-text": tokens.launcherText,
      "--chat-guest-bg": tokens.guestBubbleBackground,
      "--chat-guest-text": tokens.guestBubbleText,
      "--chat-assistant-bg": tokens.assistantBubbleBackground,
      "--chat-assistant-text": tokens.assistantBubbleText,
      "--chat-input-bg": tokens.inputBackground,
      "--chat-input-text": tokens.inputText,
      "--chat-input-border": tokens.inputBorder,
      "--chat-send-bg": tokens.sendBackground,
      "--chat-send-text": tokens.sendText,
      "--chat-focus": tokens.focusColor,
      "--chat-window-width": `${chat.width}px`,
      "--chat-window-height": `${chat.height}px`,
      "--chat-radius": `${chat.radius}px`,
      "--chat-window-shadow": tokens.shadow,
    };
    for (const [name, value] of Object.entries(variables)) root.style.setProperty(name, value);
    root.dataset.chatMode = chat.displayMode;
    root.dataset.chatPreset = chat.presetId;
    root.dataset.chatPalette = chat.paletteId;
    root.dataset.chatHeaderDesign = chat.headerDesign;
    root.dataset.chatPosition = chat.position;
    return { ...chat, tokens };
  }

  function normalize(design = {}) {
    const theme = design?.theme || {};
    const typography = design?.typography || {};
    const layout = design?.layout || {};
    const composer = design?.composer || {};
    const paletteId = typeof theme.paletteId === "string" ? theme.paletteId : "";
    const templatePaletteId = TEMPLATE_PALETTES[theme.layoutTemplateId];
    const fallback = PRESETS[paletteId] || LEGACY_PRESETS[paletteId] || PRESETS[templatePaletteId] || DEFAULTS;
    const getColor = (field, ...aliases) => {
      for (const value of [theme[field], ...aliases.map((alias) => theme[alias]), fallback[field], DEFAULTS[field]]) {
        if (isColor(value)) return value;
      }
      return DEFAULTS[field];
    };
    const background = getColor("background");
    const surface = getColor("surface");
    const bodyColor = getColor("bodyColor", "textPrimary");
    const primaryColor = getColor("primaryColor", "buttonColor", "accent");
    const secondaryColor = getColor("secondaryColor", "surface");
    const rawFont = typography.fontFamily || theme.font || fallback.fontFamily || DEFAULTS.fontFamily;
    const rawHeadingFont = typography.headingFontFamily || fallback.headingFontFamily || rawFont;
    const rawShadow = theme.shadow || fallback.shadow || DEFAULTS.shadow;
    const elevatedSurface = isColor(composer.background) ? composer.background : getColor("surfaceElevated", "composerBackground");
    const inputBackground = getColor("inputBackground", "surfaceElevated");
    const border = getColor("border");
    const buttonText = readableForeground(getColor("buttonText", "accentText"), primaryColor);
    const secondaryButtonText = readableForeground(getColor("secondaryButtonText"), secondaryColor);
    const fontFamily = fontNames.has(rawFont) ? rawFont : DEFAULTS.fontFamily;
    const headingFontFamily = fontNames.has(rawHeadingFont) ? rawHeadingFont : fontFamily;
    return {
      background,
      surface,
      surfaceElevated: elevatedSurface,
      surfaceSubtle: getColor("surfaceSubtle") || background,
      headingColor: getColor("headingColor", "textPrimary"),
      bodyColor,
      textSecondary: getColor("textSecondary"),
      accent: getColor("accent"),
      accentForeground: bodyColor,
      primaryColor,
      secondaryColor,
      buttonText,
      secondaryButtonText,
      composerBackground: elevatedSurface,
      border,
      hoverColor: getColor("hoverColor", "accent"),
      secondaryHoverColor: getColor("secondaryHoverColor") || secondaryColor,
      focusColor: getColor("focusColor", "primaryColor"),
      iconColor: getColor("iconColor", "primaryColor"),
      navBackground: getColor("navBackground") || surface,
      navText: getColor("navText") || bodyColor,
      navActiveBackground: getColor("navActiveBackground") || getColor("surfaceSubtle"),
      navActiveText: getColor("navActiveText") || primaryColor,
      menuBackground: getColor("menuBackground") || elevatedSurface,
      cardBackground: getColor("cardBackground") || surface,
      inputBackground,
      inputText: getColor("inputText") || bodyColor,
      inputPlaceholder: getColor("inputPlaceholder") || getColor("textSecondary"),
      inputBorder: getColor("inputBorder") || border,
      userMessageBackground: getColor("userMessageBackground"),
      userMessageText: readableForeground(getColor("userMessageText", "textPrimary"), getColor("userMessageBackground")),
      assistantMessageBackground: getColor("assistantMessageBackground") || elevatedSurface,
      assistantMessageText: readableForeground(getColor("assistantMessageText", "assistantText", "textPrimary"), getColor("assistantMessageBackground") || elevatedSurface),
      ...STATUS_TOKENS,
      fontFamily,
      headingFontFamily,
      density: theme.density === "compact" || theme.density === "comfortable" ? theme.density : (fallback.density || DEFAULTS.density),
      baseFontSize: Number(typography.baseFontSize || fallback.baseFontSize || DEFAULTS.baseFontSize),
      radius: Number.isFinite(Number(theme.radius)) ? Math.max(0, Math.min(32, Number(theme.radius))) : Number(fallback.radius || DEFAULTS.radius),
      shadow: ["none", "subtle", "strong"].includes(rawShadow) ? rawShadow : DEFAULTS.shadow,
      contentWidth: Number(layout.contentWidth || fallback.contentWidth || 840),
      messageWidth: Number(layout.messageWidth || fallback.messageWidth || 680),
      composerWidth: Number(layout.composerWidth || fallback.composerWidth || 720),
      messageSpacing: Number(layout.messageSpacing || fallback.messageSpacing || 24),
      paletteId,
      layoutTemplateId: typeof theme.layoutTemplateId === "string" ? theme.layoutTemplateId : "",
    };
  }

  function apply(root, design = {}) {
    const tokens = normalize(design);
    const variables = {
      "--background": tokens.background,
      "--surface": tokens.surface,
      "--surface-elevated": tokens.surfaceElevated,
      "--surface-subtle": tokens.surfaceSubtle,
      "--heading-color": tokens.headingColor,
      "--body-color": tokens.bodyColor,
      "--text-primary": tokens.bodyColor,
      "--text-secondary": tokens.textSecondary,
      "--text-muted": tokens.textSecondary,
      "--accent": tokens.accent,
      "--accent-foreground": tokens.accentForeground,
      "--primary-color": tokens.primaryColor,
      "--button-color": tokens.primaryColor,
      "--primary-hover-color": tokens.hoverColor,
      "--secondary-color": tokens.secondaryColor,
      "--secondary-hover-color": tokens.secondaryHoverColor,
      "--button-text": tokens.buttonText,
      "--secondary-button-text": tokens.secondaryButtonText,
      "--accent-text": tokens.buttonText,
      "--border": tokens.border,
      "--input-border": tokens.inputBorder,
      "--hover-color": tokens.hoverColor,
      "--focus-color": tokens.focusColor,
      "--icon-color": tokens.iconColor,
      "--nav-background": tokens.navBackground,
      "--nav-text": tokens.navText,
      "--nav-active-background": tokens.navActiveBackground,
      "--nav-active-text": tokens.navActiveText,
      "--menu-background": tokens.menuBackground,
      "--card-background": tokens.cardBackground,
      "--input-background": tokens.inputBackground,
      "--input-text": tokens.inputText,
      "--input-placeholder": tokens.inputPlaceholder,
      "--user-message-bg": tokens.userMessageBackground,
      "--user-message-text": tokens.userMessageText,
      "--assistant-message-bg": tokens.assistantMessageBackground,
      "--assistant-message-text": tokens.assistantMessageText,
      "--composer-background": tokens.composerBackground,
      "--notification-success": tokens.notificationSuccess,
      "--notification-success-background": tokens.notificationSuccessBackground,
      "--notification-warning": tokens.notificationWarning,
      "--notification-warning-background": tokens.notificationWarningBackground,
      "--notification-error": tokens.notificationError,
      "--notification-error-background": tokens.notificationErrorBackground,
      "--notification-info": tokens.notificationInfo,
      "--notification-info-background": tokens.notificationInfoBackground,
      "--guest-radius": `${tokens.radius}px`,
      "--theme-shadow": tokens.shadow === "none" ? "none" : tokens.shadow === "strong" ? "0 14px 38px rgba(25, 25, 25, .16)" : "0 7px 24px rgba(25, 25, 25, .07)",
      "--theme-font-family": tokens.fontFamily,
      "--body-font-family": tokens.fontFamily,
      "--heading-font-family": tokens.headingFontFamily,
      "--serif-display": tokens.headingFontFamily,
    };
    for (const [name, value] of Object.entries(variables)) root.style.setProperty(name, value);
    return tokens;
  }

  global.ConciergeTheme = Object.freeze({ DEFAULTS, PRESETS, TEMPLATE_PALETTES, LEGACY_PRESETS, CHAT_PRESETS, normalize, apply, normalizeChatConfig, resolveChatTokens, applyChat, contrastRatio });
})(window);
