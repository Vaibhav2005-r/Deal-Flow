import React, { useState, useEffect, useMemo } from "react";
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

const DEMO_PORTAL_USERS = [
  {
    email: "portal1@northwind.example",
    password: "Northwind Logistics Pvt Ltd",
    label: "Northwind Logistics",
    tier: "Gold Tier",
  },
  {
    email: "portal2@harbourline.example",
    password: "Harbourline Shipping",
    label: "Harbourline Shipping",
    tier: "Gold Tier",
  },
  {
    email: "portal3@calder.example",
    password: "Calder & Voss Associates",
    label: "Calder & Voss Associates",
    tier: "Gold Tier",
  },
];

interface PortalLoginProps {
  onLogin: () => void;
}

export default function PortalLogin({ onLogin }: PortalLoginProps) {
  const [activeTab, setActiveTab] = useState<"signin" | "signup">("signin");
  const [selectedDemo, setSelectedDemo] = useState<number | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const shouldReduceMotion = useReducedMotion();

  // Password strength calculation for sign-up animation
  const passwordStrength = useMemo(() => {
    if (!password) return { level: 0, text: "", color: "bg-slate-200" };
    if (password.length < 3) return { level: 25, text: "Too short", color: "bg-red-500" };
    if (password.length < 7) return { level: 60, text: "Good", color: "bg-amber-500" };
    return { level: 100, text: "Strong", color: "bg-emerald-500" };
  }, [password]);

  const isEmailValid = useMemo(() => {
    return email.includes("@") && email.includes(".") && email.length > 5;
  }, [email]);

  // Mouse follow ambient glow calculations (identical to home dashboard login)
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);

  const springConfig = { damping: 28, stiffness: 90 };
  const smoothMouseX = useSpring(mouseX, springConfig);
  const smoothMouseY = useSpring(mouseY, springConfig);

  const glowX = useTransform(smoothMouseX, (val) => `${val - 250}px`);
  const glowY = useTransform(smoothMouseY, (val) => `${val - 250}px`);

  useEffect(() => {
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

  function handleSelectDemo(index: number) {
    setSelectedDemo(index);
    setEmail(DEMO_PORTAL_USERS[index].email);
    setPassword(DEMO_PORTAL_USERS[index].password);
    setError(null);
  }

  function handleTabChange(tab: "signin" | "signup") {
    setActiveTab(tab);
    setError(null);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);

    const cleanEmail = email.trim().toLowerCase();

    try {
      if (activeTab === "signup") {
        const res = await api.post<{
          token: string;
          scope: string;
          role: string;
          full_name: string;
          user_id: number;
        }>("/api/auth/portal-signup", {
          email: cleanEmail,
          password,
          full_name: fullName.trim() || undefined,
          company_name: companyName.trim() || undefined,
        });

        setToken("portal", res.token);
        localStorage.setItem("df360.portal.user", JSON.stringify(res));
        onLogin();
      } else {
        const res = await api.post<{
          token: string;
          scope: string;
          role: string;
          full_name: string;
          user_id: number;
        }>("/api/auth/login", { email: cleanEmail, password }, "portal");

        if (res.scope !== "portal") {
          throw new Error("Invalid credentials for customer portal");
        }

        setToken("portal", res.token);
        localStorage.setItem("df360.portal.user", JSON.stringify(res));
        onLogin();
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : activeTab === "signup"
          ? "Portal account creation failed. Please check your details."
          : "Portal sign-in failed. Please check your credentials."
      );
    } finally {
      setBusy(false);
    }
  }

  // Animation variants (paced smoothly and gracefully)
  const containerVariants: Variants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: shouldReduceMotion ? 0 : 0.15,
        delayChildren: shouldReduceMotion ? 0 : 0.15,
      },
    },
  };

  const itemVariants: Variants = {
    hidden: { opacity: 0, y: shouldReduceMotion ? 0 : 14 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.75, ease: [0.16, 1, 0.3, 1] },
    },
  };

  const formVariants: Variants = {
    hidden: {
      opacity: 0,
      scale: 0.98,
      transition: { duration: 0.35, ease: "easeInOut" },
    },
    visible: {
      opacity: 1,
      scale: 1,
      transition: {
        duration: 0.6,
        staggerChildren: shouldReduceMotion ? 0 : 0.14,
        delayChildren: shouldReduceMotion ? 0 : 0.1,
      },
    },
  };

  const fieldVariants: Variants = {
    hidden: { opacity: 0, y: shouldReduceMotion ? 0 : 16 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        duration: 0.65,
        ease: [0.16, 1, 0.3, 1],
      },
    },
  };

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center overflow-x-hidden font-sans select-none p-4 sm:p-6">
      {/* Background Image Entrance Animation (30% blur for clear dashboard visibility) */}
      <motion.div
        initial={shouldReduceMotion ? { opacity: 1 } : { opacity: 0, scale: 1.04 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.5, ease: "easeOut" }}
        className="fixed inset-0 z-0 bg-cover bg-center bg-no-repeat filter brightness-115 blur-[3px]"
        style={{
          backgroundImage: `url('/portal-bg.jpg')`,
        }}
      />

      {/* Darkened/Lightened translucent overlays */}
      <div className="fixed inset-0 z-0 bg-[#160d33]/25 pointer-events-none" />
      <div className="fixed inset-0 z-0 bg-gradient-to-t from-[#0e0722]/40 via-transparent to-[#1e1245]/25 pointer-events-none" />

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

      {/* Top Left Logo and Name */}
      <motion.header
        initial={shouldReduceMotion ? { opacity: 1 } : { opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.75, ease: "easeOut" }}
        className="absolute top-5 left-5 sm:top-7 sm:left-8 z-20 flex items-center gap-3"
      >
        <DealFlowLogo size={42} showText={true} isDarkTheme={true} textSize="text-xl sm:text-2xl" />
        <span className="hidden sm:inline-block px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-white/15 text-white/90 backdrop-blur-xs border border-white/20">
          Customer Portal
        </span>
      </motion.header>

      {/* Center White Login/Signup Card Block */}
      <main className="relative z-10 w-full max-w-[430px] mx-auto my-auto pt-14 sm:pt-0">
        <motion.div
          layout
          initial={shouldReduceMotion ? { opacity: 1 } : { opacity: 0, y: 24, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{
            type: "spring",
            damping: 30,
            stiffness: 120,
            mass: 1.1,
          }}
          className="bg-white rounded-2xl shadow-2xl shadow-black/40 border border-slate-100 p-6 sm:p-8 transition-shadow duration-300 hover:shadow-black/50"
        >
          <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="visible"
          >
            {/* Header Icon & Title */}
            <motion.div variants={itemVariants} className="text-center mb-4">
              <motion.div
                whileHover={shouldReduceMotion ? {} : { rotate: [0, -6, 6, 0] }}
                transition={{ duration: 0.5 }}
                className="inline-flex items-center justify-center w-11 h-11 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-white shadow-md shadow-blue-500/20 mb-2.5 cursor-pointer"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
              </motion.div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                {activeTab === "signin" ? "Customer Portal" : "Join Customer Portal"}
              </h1>
              <p className="text-[12px] text-slate-500 mt-1">
                {activeTab === "signin"
                  ? "Sign in to review quotations, propose counter terms & confirm orders"
                  : "Create an authorized buyer account for order negotiation"}
              </p>
            </motion.div>

            {/* Tab Switcher: Sign In | Sign Up */}
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
                    layoutId="portalActiveTabUnderline"
                    className="absolute bottom-0 left-0 right-0 h-[2px] bg-[#3b5bf6]"
                    transition={{ type: "spring", stiffness: 140, damping: 22 }}
                  />
                )}
              </button>
              <button
                type="button"
                onClick={() => handleTabChange("signup")}
                className={`w-1/2 pb-2 text-xs font-semibold relative text-center transition-colors duration-200 cursor-pointer ${
                  activeTab === "signup" ? "text-[#3b5bf6]" : "text-slate-500 hover:text-slate-800"
                }`}
              >
                Sign Up
                {activeTab === "signup" && (
                  <motion.div
                    layoutId="portalActiveTabUnderline"
                    className="absolute bottom-0 left-0 right-0 h-[2px] bg-[#3b5bf6]"
                    transition={{ type: "spring", stiffness: 140, damping: 22 }}
                  />
                )}
              </button>
            </motion.div>

            {/* Quick Demo Customer Selector (Visible on Sign In tab) */}
            {activeTab === "signin" && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                className="mb-4"
              >
                <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">
                  Quick Demo Customer Preset
                </label>
                <div className="relative">
                  <select
                    value={selectedDemo ?? ""}
                    onChange={(e) => {
                      if (e.target.value !== "") {
                        handleSelectDemo(Number(e.target.value));
                      }
                    }}
                    className="w-full bg-slate-50 hover:bg-slate-100/80 border border-slate-200 rounded-lg px-3 py-2 text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-[#3b5bf6]/20 focus:border-[#3b5bf6] transition-colors cursor-pointer"
                  >
                    <option value="" disabled>Select customer account...</option>
                    {DEMO_PORTAL_USERS.map((d, i) => (
                      <option key={d.email} value={i}>
                        {d.label} ({d.tier})
                      </option>
                    ))}
                  </select>
                </div>
              </motion.div>
            )}

            {/* Error Message with Shake Animation */}
            <AnimatePresence>
              {error && (
                <motion.div
                  key="error-banner"
                  initial={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, y: -8, scale: 0.98 }}
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
                  className="mb-3.5 p-2.5 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center gap-2 shadow-xs"
                >
                  <svg className="w-3.5 h-3.5 text-red-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>{error}</span>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Form Container with Framer Motion transitions */}
            <AnimatePresence mode="wait" initial={false}>
              <motion.form
                key={activeTab}
                onSubmit={submit}
                variants={formVariants}
                initial="hidden"
                animate="visible"
                exit="hidden"
                className="space-y-3.5"
                autoComplete="off"
              >
                {/* Company / Organization Name (Sign Up only) */}
                {activeTab === "signup" && (
                  <motion.div variants={fieldVariants}>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Company / Organization Name
                    </label>
                    <div className="relative group">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400 group-focus-within:text-[#3b5bf6] transition-colors">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                        </svg>
                      </div>
                      <input
                        type="text"
                        required
                        value={companyName}
                        onChange={(e) => setCompanyName(e.target.value)}
                        placeholder="e.g. Apex Global Logistics"
                        className="w-full pl-9 pr-3 py-2 bg-white text-slate-900 border border-slate-200 rounded-lg text-xs placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[#3b5bf6]/20 focus:border-[#3b5bf6] shadow-2xs focus:shadow-xs transition-all duration-200"
                      />
                    </div>
                  </motion.div>
                )}

                {/* Contact Full Name (Sign Up only) */}
                {activeTab === "signup" && (
                  <motion.div variants={fieldVariants}>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Representative Full Name
                    </label>
                    <div className="relative group">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400 group-focus-within:text-[#3b5bf6] transition-colors">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                      </div>
                      <input
                        type="text"
                        required
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                        placeholder="e.g. Rachel Adams"
                        className="w-full pl-9 pr-3 py-2 bg-white text-slate-900 border border-slate-200 rounded-lg text-xs placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[#3b5bf6]/20 focus:border-[#3b5bf6] shadow-2xs focus:shadow-xs transition-all duration-200"
                      />
                    </div>
                  </motion.div>
                )}

                {/* Email Address */}
                <motion.div variants={fieldVariants}>
                  <div className="flex items-center justify-between mb-1">
                    <label className="block text-xs font-semibold text-slate-700">
                      {activeTab === "signup" ? "Work Email Address" : "Portal Email Address"}
                    </label>
                    {activeTab === "signup" && email && (
                      <motion.span
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className={`text-[10px] font-bold ${
                          isEmailValid ? "text-emerald-600" : "text-slate-400"
                        }`}
                      >
                        {isEmailValid ? "✓ Valid domain" : "Enter valid email"}
                      </motion.span>
                    )}
                  </div>
                  <div className="relative group">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400 group-focus-within:text-[#3b5bf6] transition-colors">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                      </svg>
                    </div>
                    <input
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder={activeTab === "signup" ? "rachel@apexlogistics.com" : "e.g. portal1@northwind.example"}
                      className="w-full pl-9 pr-3 py-2 bg-white text-slate-900 border border-slate-200 rounded-lg text-xs placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[#3b5bf6]/20 focus:border-[#3b5bf6] shadow-2xs focus:shadow-xs transition-all duration-200"
                    />
                  </div>
                </motion.div>

                {/* Password */}
                <motion.div variants={fieldVariants}>
                  <div className="flex items-center justify-between mb-1">
                    <label className="block text-xs font-semibold text-slate-700">
                      {activeTab === "signup" ? "Choose Password" : "Portal Password"}
                    </label>
                    {activeTab === "signup" && password && (
                      <motion.span
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="text-[10px] font-bold text-slate-500"
                      >
                        {passwordStrength.text}
                      </motion.span>
                    )}
                  </div>
                  <div className="relative group">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400 group-focus-within:text-[#3b5bf6] transition-colors">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                      </svg>
                    </div>
                    <input
                      type={showPassword ? "text" : "password"}
                      required
                      minLength={3}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder={activeTab === "signup" ? "At least 3 characters" : "Enter your customer password"}
                      className="w-full pl-9 pr-10 py-2 bg-white text-slate-900 border border-slate-200 rounded-lg text-xs placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-[#3b5bf6]/20 focus:border-[#3b5bf6] shadow-2xs focus:shadow-xs transition-all duration-200"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
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
                    </button>
                  </div>

                  {/* Animated Password Strength Bar in Sign Up */}
                  {activeTab === "signup" && password && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="mt-1.5 w-full bg-slate-100 rounded-full h-1 overflow-hidden"
                    >
                      <motion.div
                        className={`h-full ${passwordStrength.color}`}
                        initial={{ width: 0 }}
                        animate={{ width: `${passwordStrength.level}%` }}
                        transition={{ duration: 0.65, ease: "easeOut" }}
                      />
                    </motion.div>
                  )}
                </motion.div>

                {/* Options Row */}
                <motion.div variants={fieldVariants} className="flex items-center justify-between pt-1">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={rememberMe}
                      onChange={(e) => setRememberMe(e.target.checked)}
                      className="w-3.5 h-3.5 rounded border-slate-300 text-[#3b5bf6] focus:ring-[#3b5bf6]/30 cursor-pointer"
                    />
                    <span className="text-xs text-slate-600">Remember session</span>
                  </label>
                  <span className="text-[11px] text-slate-400">
                    Scope: <code className="bg-slate-100 px-1 py-0.5 rounded text-slate-600">portal</code>
                  </span>
                </motion.div>

                {/* Submit Button with Hover & Tap Spring Motion */}
                <motion.div variants={fieldVariants} className="pt-1">
                  <motion.button
                    type="submit"
                    disabled={busy}
                    whileHover={shouldReduceMotion || busy ? {} : { scale: 1.015 }}
                    whileTap={shouldReduceMotion || busy ? {} : { scale: 0.985 }}
                    className="relative overflow-hidden w-full bg-[#1d72f2] hover:bg-[#155ecc] text-white rounded-lg px-4 py-2.5 text-xs font-semibold shadow-md shadow-blue-500/25 transition-colors disabled:opacity-50 flex items-center justify-center gap-2 cursor-pointer group"
                  >
                    {/* Subtle button sheen animation */}
                    {!shouldReduceMotion && (
                      <motion.div
                        className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent pointer-events-none"
                        initial={{ x: "-100%" }}
                        whileHover={{ x: "100%" }}
                        transition={{ duration: 1.2, ease: "easeInOut" }}
                      />
                    )}

                    {busy ? (
                      <>
                        <svg className="animate-spin h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        <span>{activeTab === "signup" ? "Creating portal account…" : "Authenticating portal…"}</span>
                      </>
                    ) : (
                      <span>
                        {activeTab === "signup"
                          ? "Create Customer Account →"
                          : "Sign In to Customer Portal →"}
                      </span>
                    )}
                  </motion.button>
                </motion.div>
              </motion.form>
            </AnimatePresence>

            {/* Bottom Switcher: Back to Internal Console */}
            <motion.div variants={itemVariants} className="mt-5 pt-4 border-t border-slate-100 text-center">
              <a
                href="/login"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-[#1d72f2] transition-colors"
              >
                <span>← Switch to Internal Employee Console</span>
              </a>
            </motion.div>
          </motion.div>
        </motion.div>
      </main>
    </div>
  );
}
