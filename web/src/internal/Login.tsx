import React, { useState, useEffect } from "react";
import {
  motion,
  AnimatePresence,
  useMotionValue,
  useSpring,
  useTransform,
  useReducedMotion,
  type Variants,
} from "framer-motion";
import { api } from "@/lib/api";
import { setToken } from "@/lib/auth";
import { DealFlowLogo } from "@/components/Logo";

interface RoleOption {
  id: "rep" | "manager" | "finance";
  label: string;
}

/**
 * Only the role self-service registration can actually grant.
 *
 * The form previously offered Manager and Finance. The server ignores a
 * claimed role and creates a rep, so choosing "Manager" told the user
 * something untrue -- and until this commit the /register endpoint DID honour
 * it, which let anyone mint themselves an admin. Approver roles are granted by
 * an existing admin, never at a public sign-up form.
 */
const ROLES: RoleOption[] = [{ id: "rep", label: "Sales Rep" }];

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [activeTab, setActiveTab] = useState<"signin" | "create">("signin");
  const [selectedRole, setSelectedRole] = useState<"rep" | "manager" | "finance">("rep");
  const [fullName, setFullName] = useState<string>("");
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [showPassword, setShowPassword] = useState<boolean>(false);
  const [rememberMe, setRememberMe] = useState<boolean>(false);
  const [agreedToTerms, setAgreedToTerms] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const shouldReduceMotion = useReducedMotion();

  // Mouse follow ambient glow calculations
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  const springConfig = { damping: 28, stiffness: 90 };
  const smoothMouseX = useSpring(mouseX, springConfig);
  const smoothMouseY = useSpring(mouseY, springConfig);

  const glowX = useTransform(smoothMouseX, (val) => `${val - 250}px`);
  const glowY = useTransform(smoothMouseY, (val) => `${val - 250}px`);

  useEffect(() => {
    // Center glow initially
    mouseX.set(window.innerWidth / 2);
    mouseY.set(window.innerHeight / 2);

    const handleMouseMove = (e: MouseEvent) => {
      if (!shouldReduceMotion) {
        mouseX.set(e.clientX);
        mouseY.set(e.clientY);
      }
    };

    window.addEventListener("mousemove", handleMouseMove, { passive: true });
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, [mouseX, mouseY, shouldReduceMotion]);

  const handleSelectRole = (role: "rep" | "manager" | "finance") => {
    setSelectedRole(role);
    setError(null);
    setSuccessMessage(null);
    setToastMessage(null);
  };

  const handleTabChange = (tab: "signin" | "create") => {
    setActiveTab(tab);
    setError(null);
    setSuccessMessage(null);
    setToastMessage(null);
  };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setToastMessage(null);

    const cleanEmail = email.trim().toLowerCase();

    if (activeTab === "create") {
      setBusy(true);
      try {
        const res = await api.post<{
          token: string;
          role: string;
          full_name: string;
          user_id: number;
          email?: string;
        }>("/api/auth/register", {
          email: cleanEmail,
          password,
          full_name: fullName.trim() || undefined,
          role: selectedRole,
        });

        // Automatically log the user in with their newly created account
        setToken("internal", res.token);
        localStorage.setItem(
          "df360.internal.user",
          JSON.stringify({
            ...res,
            email: res.email || cleanEmail,
            // the GRANTED role from the server, never the one requested
            role: res.role,
          })
        );
        onLogin();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create account. Please check your details.");
      } finally {
        setBusy(false);
      }
      return;
    }

    setBusy(true);
    try {
      const res = await api.post<{
        token: string;
        role: string;
        scope?: string;
        full_name: string;
        user_id: number;
        email?: string;
      }>("/api/auth/login", { email: cleanEmail, password });

      // One form, two audiences. The server derives the scope from the account,
      // so a customer signs in here with their own credentials and lands in the
      // portal -- rather than having to know a separate URL. The two scopes are
      // stored under different keys and are never interchangeable.
      if (res.scope === "portal" || res.role === "portal") {
        setToken("portal", res.token);
        localStorage.setItem(
          "df360.portal.user",
          JSON.stringify({ ...res, email: res.email || cleanEmail })
        );
        window.location.assign("/portal");
        return;
      }

      setToken("internal", res.token);
      localStorage.setItem(
        "df360.internal.user",
        JSON.stringify({
          ...res,
          email: res.email || cleanEmail,
          // the GRANTED role from the server, never the one requested
          role: res.role,
        })
      );
      onLogin();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid credentials. Please check your email and password.");
    } finally {
      setBusy(false);
    }
  }

  const showDemoNotice = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  // Stagger animation variants for card contents
  const containerVariants: Variants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: shouldReduceMotion ? 0 : 0.08,
        delayChildren: shouldReduceMotion ? 0 : 0.12,
      },
    },
  };

  const itemVariants: Variants = {
    hidden: { opacity: 0, y: shouldReduceMotion ? 0 : 10 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.45, ease: "easeOut" },
    },
  };

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center overflow-x-hidden font-sans select-none p-4 sm:p-6">
      {/* Background Image Entrance Animation */}
      <motion.div
        initial={shouldReduceMotion ? { opacity: 1 } : { opacity: 0, scale: 1.04 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.5, ease: "easeOut" }}
        className="fixed inset-0 z-0 bg-cover bg-center bg-no-repeat filter brightness-135 blur-[6px]"
        style={{
          backgroundImage: `url('/auth-bg.jpg')`,
        }}
      />

      {/* Darkened/Lightened translucent overlays */}
      <div className="fixed inset-0 z-0 bg-[#160d33]/20 pointer-events-none" />
      <div className="fixed inset-0 z-0 bg-gradient-to-t from-[#0e0722]/35 via-transparent to-[#1e1245]/20 pointer-events-none" />

      {/* Subtle Mouse-Follow Ambient Glow (Behind Card) */}
      {!shouldReduceMotion && (
        <motion.div
          className="fixed pointer-events-none z-0 w-[500px] h-[500px] rounded-full bg-gradient-to-tr from-blue-600/20 via-indigo-500/15 to-purple-500/20 blur-[100px] opacity-70"
          style={{
            left: glowX,
            top: glowY,
          }}
        />
      )}

      {/* Top Left Logo and Name of Prototype */}
      <motion.header
        initial={shouldReduceMotion ? { opacity: 1 } : { opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.75, ease: "easeOut" }}
        className="absolute top-5 left-5 sm:top-7 sm:left-8 z-20"
      >
        <DealFlowLogo size={42} showText={true} isDarkTheme={true} textSize="text-xl sm:text-2xl" />
      </motion.header>

      {/* Center White Login Card Block */}
      <main className="relative z-10 w-full max-w-[420px] mx-auto my-auto pt-14 sm:pt-0">
        <motion.div
          layout
          initial={shouldReduceMotion ? { opacity: 1 } : { opacity: 0, y: 24, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{
            type: "spring",
            damping: 28,
            stiffness: 200,
            mass: 1,
          }}
          className="bg-white rounded-2xl shadow-2xl shadow-black/40 border border-slate-100 p-6 sm:p-8 transition-shadow duration-300 hover:shadow-black/50"
        >
          <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="visible"
          >
            {/* Dynamic Heading based on Active Tab */}
            <motion.div variants={itemVariants} className="text-center mb-5">
              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={activeTab}
                  initial={shouldReduceMotion ? { opacity: 1 } : { opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, y: -6 }}
                  transition={{ duration: 0.28 }}
                >
                  <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                    {activeTab === "signin" ? "Welcome back" : "Create your workspace"}
                  </h1>
                  <p className="text-[12px] text-slate-500 mt-1">
                    {activeTab === "signin"
                      ? "Sign in to your DealFlow360 account"
                      : "Get started with DealFlow360 revenue platform"}
                  </p>
                </motion.div>
              </AnimatePresence>
            </motion.div>

            {/* Tab Switcher: Sign In | Create Account */}
            <motion.div variants={itemVariants} className="border-b border-slate-200 flex mb-4 relative">
              <button
                type="button"
                onClick={() => handleTabChange("signin")}
                className={`w-1/2 pb-2 text-xs font-semibold relative text-center transition-colors duration-200 cursor-pointer ${
                  activeTab === "signin" ? "text-[#3b5bf6]" : "text-slate-500 hover:text-slate-800"
                }`}
              >
                Sign In
                {activeTab === "signin" && (
                  <motion.div
                    layoutId="activeTabUnderline"
                    className="absolute bottom-0 left-0 right-0 h-[2px] bg-[#3b5bf6]"
                    transition={{ type: "spring", stiffness: 360, damping: 32 }}
                  />
                )}
              </button>
              <button
                type="button"
                onClick={() => handleTabChange("create")}
                className={`w-1/2 pb-2 text-xs font-semibold relative text-center transition-colors duration-200 cursor-pointer ${
                  activeTab === "create" ? "text-[#3b5bf6]" : "text-slate-500 hover:text-slate-800"
                }`}
              >
                Create Account
                {activeTab === "create" && (
                  <motion.div
                    layoutId="activeTabUnderline"
                    className="absolute bottom-0 left-0 right-0 h-[2px] bg-[#3b5bf6]"
                    transition={{ type: "spring", stiffness: 360, damping: 32 }}
                  />
                )}
              </button>
            </motion.div>

            {/* Role Selector Pills with Framer Motion layoutId */}
            <motion.div variants={itemVariants} className="grid grid-cols-3 gap-2 mb-4 p-0.5 bg-slate-100/70 rounded-xl">
              {ROLES.map((roleItem) => {
                const isSelected = selectedRole === roleItem.id;
                return (
                  <button
                    key={roleItem.id}
                    type="button"
                    onClick={() => handleSelectRole(roleItem.id)}
                    className={`relative py-1.5 px-2 rounded-lg text-center font-semibold text-xs transition-colors duration-200 capitalize z-10 cursor-pointer ${
                      isSelected ? "text-[#3b5bf6]" : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    {isSelected && (
                      <motion.div
                        layoutId="activeRoleIndicator"
                        className="absolute inset-0 bg-white rounded-lg shadow-xs border border-slate-200/90 z-[-1]"
                        transition={{ type: "spring", stiffness: 360, damping: 30 }}
                      />
                    )}
                    {roleItem.label}
                  </button>
                );
              })}
            </motion.div>

            {/* Feedback & Error Message Banners with Shake Animation */}
            <AnimatePresence>
              {successMessage && (
                <motion.div
                  key="success-banner"
                  initial={{ opacity: 0, y: -8, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -6, scale: 0.98 }}
                  transition={{ duration: 0.35 }}
                  className="mb-3.5 p-3 bg-emerald-50 border border-emerald-200/90 rounded-xl text-xs text-emerald-800 flex items-start gap-2.5 shadow-xs"
                >
                  <svg className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
                  </svg>
                  <div>
                    <p className="font-bold text-emerald-900">Account created successfully!</p>
                    <p className="text-[11px] text-emerald-700 mt-0.5">{successMessage}</p>
                  </div>
                </motion.div>
              )}

              {error && (
                <motion.div
                  key="error-banner"
                  initial={
                    shouldReduceMotion
                      ? { opacity: 0 }
                      : { opacity: 0, y: -8, scale: 0.98 }
                  }
                  animate={
                    shouldReduceMotion
                      ? { opacity: 1 }
                      : {
                          opacity: 1,
                          y: 0,
                          scale: 1,
                          x: [0, -5, 5, -4, 4, -2, 2, 0],
                        }
                  }
                  exit={{ opacity: 0, y: -6, scale: 0.98 }}
                  transition={{ duration: 0.42, ease: "easeOut" }}
                  className="mb-3 p-2.5 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center gap-2 shadow-xs"
                >
                  <svg className="w-3.5 h-3.5 text-red-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>{error}</span>
                </motion.div>
              )}

              {toastMessage && (
                <motion.div
                  key="toast-banner"
                  initial={{ opacity: 0, y: -8, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -6, scale: 0.98 }}
                  transition={{ duration: 0.35 }}
                  className="mb-3 p-2.5 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-800 flex items-center gap-2 shadow-xs"
                >
                  <svg className="w-3.5 h-3.5 text-[#3b5bf6] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>{toastMessage}</span>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Form Container with AnimatePresence for Sign In ↔ Create Account */}
            <AnimatePresence mode="wait" initial={false}>
              <motion.form
                key={activeTab}
                onSubmit={submit}
                initial={
                  shouldReduceMotion
                    ? { opacity: 1 }
                    : { opacity: 0, x: activeTab === "create" ? 14 : -14 }
                }
                animate={{ opacity: 1, x: 0 }}
                exit={
                  shouldReduceMotion
                    ? { opacity: 0 }
                    : { opacity: 0, x: activeTab === "create" ? -14 : 14 }
                }
                transition={{ duration: 0.28, ease: "easeInOut" }}
                className="space-y-3.5"
                autoComplete="off"
              >
                {/* Full Name (Create Account only) */}
                {activeTab === "create" && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Full Name
                    </label>
                    <div className="relative group">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400 group-focus-within:text-[#3b5bf6] transition-colors">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                      </div>
                      <input
                        type="text"
                        name="dealflow_fullname"
                        id="dealflow_fullname"
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                        placeholder="Enter your full name"
                        autoComplete="name"
                        className="w-full pl-9 pr-3 py-2 bg-white text-slate-900 border border-slate-200 rounded-lg text-xs placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[#3b5bf6]/20 focus:border-[#3b5bf6] shadow-2xs focus:shadow-xs transition-all duration-200"
                      />
                    </div>
                  </motion.div>
                )}

                {/* Work Email */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Work Email
                  </label>
                  <div className="relative group">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400 group-focus-within:text-[#3b5bf6] transition-colors">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                      </svg>
                    </div>
                    <input
                      type="email"
                      name="dealflow_work_email"
                      id="dealflow_work_email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="Enter your work email"
                      autoComplete="off"
                      className="w-full pl-9 pr-3 py-2 bg-white text-slate-900 border border-slate-200 rounded-lg text-xs placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[#3b5bf6]/20 focus:border-[#3b5bf6] shadow-2xs focus:shadow-xs transition-all duration-200"
                    />
                  </div>
                </div>

                {/* Password */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Password
                  </label>
                  <div className="relative group">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400 group-focus-within:text-[#3b5bf6] transition-colors">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                      </svg>
                    </div>
                    <input
                      type={showPassword ? "text" : "password"}
                      name="dealflow_work_password"
                      id="dealflow_work_password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder={activeTab === "create" ? "Create a password" : "Enter your password"}
                      autoComplete="new-password"
                      className="w-full pl-9 pr-9 py-2 bg-white text-slate-900 border border-slate-200 rounded-lg text-xs placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[#3b5bf6]/20 focus:border-[#3b5bf6] shadow-2xs focus:shadow-xs transition-all duration-200 font-mono"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
                      aria-label="Toggle password visibility"
                    >
                      <AnimatePresence mode="wait" initial={false}>
                        <motion.div
                          key={showPassword ? "eye-open" : "eye-closed"}
                          initial={{ opacity: 0, scale: 0.8 }}
                          animate={{ opacity: 1, scale: 1 }}
                          exit={{ opacity: 0, scale: 0.8 }}
                          transition={{ duration: 0.15 }}
                        >
                          {showPassword ? (
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
                            </svg>
                          ) : (
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                            </svg>
                          )}
                        </motion.div>
                      </AnimatePresence>
                    </button>
                  </div>
                </div>

                {/* Remember Me & Forgot Password (Sign In) or Terms Agreement (Create Account) */}
                <div className="flex items-center justify-between pt-0.5">
                  <label className="flex items-center gap-2 cursor-pointer group">
                    <motion.div
                      whileTap={{ scale: 0.9 }}
                      className="relative flex items-center justify-center"
                    >
                      <input
                        type="checkbox"
                        checked={activeTab === "signin" ? rememberMe : agreedToTerms}
                        onChange={(e) =>
                          activeTab === "signin"
                            ? setRememberMe(e.target.checked)
                            : setAgreedToTerms(e.target.checked)
                        }
                        className="w-3.5 h-3.5 text-[#3b5bf6] rounded border-slate-300 focus:ring-[#3b5bf6] cursor-pointer transition-all"
                      />
                    </motion.div>
                    <span className="text-[11px] text-slate-600 group-hover:text-slate-900 transition-colors font-normal">
                      {activeTab === "signin" ? "Remember me" : "I agree to Terms & Privacy Policy"}
                    </span>
                  </label>

                  {activeTab === "signin" && (
                    <button
                      type="button"
                      onClick={() => showDemoNotice("Password reset instructions will be sent to your work email.")}
                      className="text-[11px] font-semibold text-[#3b5bf6] hover:text-[#2d4de6] hover:underline transition-colors cursor-pointer"
                    >
                      Forgot password?
                    </button>
                  )}
                </div>

                {/* Animated Submit Button with Hover, Tap & Loading State */}
                <motion.button
                  type="submit"
                  disabled={busy}
                  whileHover={shouldReduceMotion || busy ? {} : { scale: 1.015 }}
                  whileTap={shouldReduceMotion || busy ? {} : { scale: 0.985 }}
                  transition={{ duration: 0.15 }}
                  className="w-full bg-[#3b5bf6] hover:bg-[#2d4de6] active:bg-[#2040d6] text-white rounded-lg py-2.5 px-4 text-xs font-semibold transition-colors shadow-md shadow-[#3b5bf6]/25 hover:shadow-lg hover:shadow-[#3b5bf6]/35 disabled:opacity-60 flex items-center justify-center gap-1.5 cursor-pointer group"
                >
                  {busy ? (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="flex items-center justify-center gap-1.5"
                    >
                      <svg className="animate-spin -ml-1 mr-1 h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      <span>{activeTab === "signin" ? "Signing in…" : "Creating account…"}</span>
                    </motion.div>
                  ) : (
                    <span className="flex items-center gap-1.5">
                      <span>{activeTab === "signin" ? "Sign In" : "Create Account"}</span>
                      <svg
                        className="w-3.5 h-3.5 transition-transform duration-200 group-hover:translate-x-0.5"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                      </svg>
                    </span>
                  )}
                </motion.button>
              </motion.form>
            </AnimatePresence>

            {/* Card Footer Switcher Link */}
            <motion.div variants={itemVariants} className="mt-5 text-center">
              {activeTab === "signin" ? (
                <p className="text-[11px] text-slate-500">
                  Don't have an account?{" "}
                  <button
                    type="button"
                    onClick={() => {
                      setActiveTab("create");
                      setError(null);
                      setToastMessage(null);
                    }}
                    className="font-bold text-[#3b5bf6] hover:text-[#2d4de6] hover:underline cursor-pointer transition-colors"
                  >
                    Create Account
                  </button>
                </p>
              ) : (
                <p className="text-[11px] text-slate-500">
                  Already have an account?{" "}
                  <button
                    type="button"
                    onClick={() => {
                      setActiveTab("signin");
                      setError(null);
                      setToastMessage(null);
                    }}
                    className="font-bold text-[#3b5bf6] hover:text-[#2d4de6] hover:underline cursor-pointer transition-colors"
                  >
                    Sign In
                  </button>
                </p>
              )}
            </motion.div>
          </motion.div>
        </motion.div>
      </main>
    </div>
  );
}
