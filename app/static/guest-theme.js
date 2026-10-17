(function installConciergeTheme(global) {
  const DEFAULTS = Object.freeze({
    background: "#faf8f4",
    surface: "#ffffff",
    headingColor: "#1c1c1c",
    bodyColor: "#1c1c1c",
    textSecondary: "#6e6a64",
    accent: "#b38a4a",
    primaryColor: "#b38a4a",
    secondaryColor: "#ffffff",
    buttonText: "#1c1c1c",
    composerBackground: "#ffffff",
    border: "#e8e3da",
    hoverColor: "#9a7136",
    focusColor: "#80602f",
    userMessageBackground: "#f0ede7",
    userMessageText: "#1c1c1c",
    assistantText: "#1c1c1c",
    userMessageText: "#1c1c1c",
    fontFamily: "Geist",
    radius: 14,
    shadow: "subtle",
    density: "comfortable",
    baseFontSize: 15,
  });

  const PRESETS = Object.freeze({
    elegant: { background: "#f5f5f5", surface: "#ffffff", headingColor: "#202020", bodyColor: "#202020", textSecondary: "#666666", accent: "#444444", primaryColor: "#202020", secondaryColor: "#eeeeee", buttonText: "#ffffff", composerBackground: "#ffffff", border: "#dedede", hoverColor: "#333333", focusColor: "#444444", userMessageBackground: "#ededed", fontFamily: "Playfair Display", density: "comfortable", baseFontSize: 15, contentWidth: 840, messageWidth: 660, composerWidth: 820, messageSpacing: 27, radius: 8, shadow: "subtle" },
    minimal: { background: "#f7f7f7", surface: "#ffffff", headingColor: "#171717", bodyColor: "#171717", textSecondary: "#686868", accent: "#111111", primaryColor: "#111111", secondaryColor: "#eeeeee", buttonText: "#ffffff", composerBackground: "#ffffff", border: "#e2e2e2", hoverColor: "#292929", focusColor: "#111111", userMessageBackground: "#eeeeee", fontFamily: "Inter", density: "comfortable", baseFontSize: 15, contentWidth: 840, messageWidth: 680, composerWidth: 840, messageSpacing: 24, radius: 8, shadow: "subtle" },
    "soft-gray": { background: "#f1f1f1", surface: "#ffffff", headingColor: "#222222", bodyColor: "#222222", textSecondary: "#6b6b6b", accent: "#444444", primaryColor: "#222222", secondaryColor: "#e8e8e8", buttonText: "#ffffff", composerBackground: "#ffffff", border: "#dddddd", hoverColor: "#353535", focusColor: "#444444", userMessageBackground: "#e8e8e8", fontFamily: "Geist", density: "comfortable", baseFontSize: 15, contentWidth: 840, messageWidth: 680, composerWidth: 840, messageSpacing: 26, radius: 12, shadow: "subtle" },
    "high-contrast": { background: "#ececec", surface: "#ffffff", headingColor: "#111111", bodyColor: "#111111", textSecondary: "#4d4d4d", accent: "#111111", primaryColor: "#111111", secondaryColor: "#e1e1e1", buttonText: "#ffffff", composerBackground: "#ffffff", border: "#b8b8b8", hoverColor: "#000000", focusColor: "#005fcc", userMessageBackground: "#e1e1e1", fontFamily: "Inter", density: "compact", baseFontSize: 15, contentWidth: 840, messageWidth: 620, composerWidth: 800, messageSpacing: 20, radius: 5, shadow: "none" },
    graphite: { background: "#202020", surface: "#292929", headingColor: "#f4f4f4", bodyColor: "#f4f4f4", textSecondary: "#b5b5b5", accent: "#f1f1f1", primaryColor: "#f1f1f1", secondaryColor: "#3b3b3b", buttonText: "#171717", composerBackground: "#303030", border: "#454545", hoverColor: "#ffffff", focusColor: "#f1f1f1", userMessageBackground: "#3b3b3b", userMessageText: "#f4f4f4", fontFamily: "Inter", density: "comfortable", baseFontSize: 15, contentWidth: 840, messageWidth: 680, composerWidth: 840, messageSpacing: 24, radius: 8, shadow: "subtle" },
    ocean: { background: "#edf5f6", surface: "#ffffff", headingColor: "#183039", bodyColor: "#183039", textSecondary: "#566b70", accent: "#287987", primaryColor: "#236a78", secondaryColor: "#dcecef", buttonText: "#ffffff", composerBackground: "#ffffff", border: "#c8dfe2", hoverColor: "#1b5662", focusColor: "#287987", userMessageBackground: "#dcecef", fontFamily: "Geist", density: "comfortable", baseFontSize: 15, contentWidth: 840, messageWidth: 680, composerWidth: 840, messageSpacing: 24, radius: 8, shadow: "subtle" },
    botanical: { background: "#f1f5f1", surface: "#ffffff", headingColor: "#20302a", bodyColor: "#20302a", textSecondary: "#5e6f64", accent: "#4b7659", primaryColor: "#3a6248", secondaryColor: "#e0eae2", buttonText: "#ffffff", composerBackground: "#ffffff", border: "#cfddd1", hoverColor: "#2f513b", focusColor: "#4b7659", userMessageBackground: "#e0eae2", fontFamily: "Geist", density: "comfortable", baseFontSize: 15, contentWidth: 840, messageWidth: 680, composerWidth: 840, messageSpacing: 24, radius: 8, shadow: "subtle" },
    rose: { background: "#f7f1f4", surface: "#ffffff", headingColor: "#322730", bodyColor: "#322730", textSecondary: "#74636d", accent: "#98677f", primaryColor: "#83556c", secondaryColor: "#efe1e9", buttonText: "#ffffff", composerBackground: "#ffffff", border: "#e4d4dc", hoverColor: "#70445b", focusColor: "#98677f", userMessageBackground: "#efe1e9", fontFamily: "Inter", density: "comfortable", baseFontSize: 15, contentWidth: 840, messageWidth: 680, composerWidth: 840, messageSpacing: 24, radius: 8, shadow: "subtle" },
    coral: { background: "#f8f1ef", surface: "#ffffff", headingColor: "#332723", bodyColor: "#332723", textSecondary: "#76625c", accent: "#ad5d4d", primaryColor: "#994d3e", secondaryColor: "#f2dfda", buttonText: "#ffffff", composerBackground: "#ffffff", border: "#e5d2cc", hoverColor: "#7f3e32", focusColor: "#ad5d4d", userMessageBackground: "#f2dfda", fontFamily: "Inter", density: "comfortable", baseFontSize: 15, contentWidth: 840, messageWidth: 680, composerWidth: 840, messageSpacing: 24, radius: 8, shadow: "subtle" },
    "modern-elegance": { background: "#f5f4f0", surface: "#ffffff", headingColor: "#262a27", bodyColor: "#262a27", textSecondary: "#686c68", accent: "#78633c", primaryColor: "#304239", secondaryColor: "#ece9e1", buttonText: "#ffffff", composerBackground: "#ffffff", border: "#dedbd2", hoverColor: "#25342d", focusColor: "#78633c", userMessageBackground: "#ece9e1", fontFamily: "Playfair Display", density: "comfortable", baseFontSize: 15, contentWidth: 840, messageWidth: 660, composerWidth: 820, messageSpacing: 28, radius: 8, shadow: "subtle" },
  });

  const TEMPLATE_PALETTES = Object.freeze({
    luxury: "modern-elegance",
    elegant: "elegant",
    minimal: "minimal",
    business: "high-contrast",
    resort: "ocean",
    restaurant: "coral",
    blank: "minimal",
  });

  const isColor = (value) => typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value);

  function normalize(design = {}) {
    const theme = design?.theme || {};
    const typography = design?.typography || {};
    const layout = design?.layout || {};
    const composer = design?.composer || {};
    const fallback = PRESETS[theme.paletteId] || {};
    const getColor = (field, ...aliases) => {
      for (const value of [theme[field], ...aliases.map((alias) => theme[alias]), fallback[field], DEFAULTS[field]]) {
        if (isColor(value)) return value;
      }
      return DEFAULTS[field];
    };
    const rawFont = typography.fontFamily || theme.font || fallback.fontFamily || DEFAULTS.fontFamily;
    const allowedFonts = new Set(["Geist", "Inter", "Manrope", "DM Sans", "Poppins", "Montserrat", "Lato", "Merriweather", "Playfair Display", "system-ui"]);
    const rawShadow = theme.shadow || fallback.shadow || DEFAULTS.shadow;
    return {
      background: getColor("background"),
      surface: getColor("surface"),
      headingColor: getColor("headingColor", "textPrimary"),
      bodyColor: getColor("bodyColor", "textPrimary"),
      textSecondary: getColor("textSecondary"),
      accent: getColor("accent"),
      primaryColor: getColor("primaryColor", "buttonColor", "accent"),
      secondaryColor: getColor("secondaryColor", "surface"),
      buttonText: getColor("buttonText", "accentText"),
      composerBackground: isColor(composer.background) ? composer.background : getColor("composerBackground"),
      border: getColor("border"),
      hoverColor: getColor("hoverColor", "accent"),
      focusColor: getColor("focusColor", "accent"),
      userMessageBackground: getColor("userMessageBackground"),
      userMessageText: getColor("userMessageText", "textPrimary"),
      assistantText: getColor("assistantText", "textPrimary"),
      fontFamily: allowedFonts.has(rawFont) ? rawFont : DEFAULTS.fontFamily,
      density: theme.density === "compact" || theme.density === "comfortable" ? theme.density : (fallback.density || DEFAULTS.density),
      baseFontSize: Number(typography.baseFontSize || fallback.baseFontSize || DEFAULTS.baseFontSize),
      radius: Number.isFinite(Number(theme.radius)) ? Math.max(0, Math.min(32, Number(theme.radius))) : Number(fallback.radius || DEFAULTS.radius),
      shadow: ["none", "subtle", "strong"].includes(rawShadow) ? rawShadow : DEFAULTS.shadow,
      contentWidth: Number(layout.contentWidth || fallback.contentWidth || 840),
      messageWidth: Number(layout.messageWidth || fallback.messageWidth || 680),
      composerWidth: Number(layout.composerWidth || fallback.composerWidth || 720),
      messageSpacing: Number(layout.messageSpacing || fallback.messageSpacing || 24),
      paletteId: typeof theme.paletteId === "string" ? theme.paletteId : "",
      layoutTemplateId: typeof theme.layoutTemplateId === "string" ? theme.layoutTemplateId : "",
    };
  }

  function apply(root, design = {}) {
    const tokens = normalize(design);
    const variables = {
      "--background": tokens.background,
      "--surface": tokens.surface,
      "--surface-elevated": tokens.composerBackground,
      "--heading-color": tokens.headingColor,
      "--body-color": tokens.bodyColor,
      "--text-primary": tokens.bodyColor,
      "--text-secondary": tokens.textSecondary,
      "--text-muted": tokens.textSecondary,
      "--accent": tokens.accent,
      "--primary-color": tokens.primaryColor,
      "--button-color": tokens.primaryColor,
      "--secondary-color": tokens.secondaryColor,
      "--button-text": tokens.buttonText,
      "--accent-text": tokens.buttonText,
      "--border": tokens.border,
      "--hover-color": tokens.hoverColor,
      "--focus-color": tokens.focusColor,
      "--user-message-bg": tokens.userMessageBackground,
      "--user-message-text": tokens.userMessageText,
      "--assistant-text": tokens.assistantText,
      "--composer-background": tokens.composerBackground,
      "--guest-radius": `${tokens.radius}px`,
      "--theme-shadow": tokens.shadow === "none" ? "none" : tokens.shadow === "strong" ? "0 14px 38px rgba(25, 25, 25, .16)" : "0 7px 24px rgba(25, 25, 25, .07)",
      "--theme-font-family": tokens.fontFamily,
    };
    for (const [name, value] of Object.entries(variables)) root.style.setProperty(name, value);
    return tokens;
  }

  global.ConciergeTheme = Object.freeze({ DEFAULTS, PRESETS, TEMPLATE_PALETTES, normalize, apply });
})(window);
