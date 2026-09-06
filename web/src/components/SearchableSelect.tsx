import React, { useState, useRef, useEffect, useId } from "react";

export interface SelectOption {
  value: string | number;
  label: string;
  sublabel?: string;
  disabled?: boolean;
}

export interface SearchableSelectProps {
  options: SelectOption[];
  value: string | number | null | undefined;
  onChange: (value: any) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  disabled?: boolean;
  className?: string;
  containerClassName?: string;
  dataTestId?: string;
  name?: string;
  id?: string;
  variant?: "light" | "dark";
  required?: boolean;
}

export default function SearchableSelect({
  options,
  value,
  onChange,
  placeholder = "Select an option...",
  searchPlaceholder = "Search...",
  disabled = false,
  className = "",
  containerClassName = "",
  dataTestId,
  name,
  id,
  variant = "light",
  required = false,
}: SearchableSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [highlightedIndex, setHighlightedIndex] = useState(0);

  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const generatedId = useId();
  const selectId = id || generatedId;

  // Find currently selected option
  const selectedOption = options.find((opt) => String(opt.value) === String(value));

  // Filter options by search query
  const filteredOptions = options.filter((opt) => {
    if (!searchQuery.trim()) return true;
    const query = searchQuery.toLowerCase();
    const labelMatch = opt.label.toLowerCase().includes(query);
    const sublabelMatch = opt.sublabel ? opt.sublabel.toLowerCase().includes(query) : false;
    const valueMatch = String(opt.value).toLowerCase().includes(query);
    return labelMatch || sublabelMatch || valueMatch;
  });

  // Handle clicking outside to close
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  // Focus search input when dropdown opens
  useEffect(() => {
    if (isOpen) {
      setSearchQuery("");
      setHighlightedIndex(0);
      setTimeout(() => {
        searchInputRef.current?.focus();
      }, 50);
    }
  }, [isOpen]);

  // Keep highlighted option in view when navigating via arrow keys
  useEffect(() => {
    if (isOpen && listRef.current && listRef.current.children[highlightedIndex]) {
      const el = listRef.current.children[highlightedIndex] as HTMLElement;
      el.scrollIntoView({ block: "nearest" });
    }
  }, [highlightedIndex, isOpen]);

  function handleSelect(option: SelectOption) {
    if (option.disabled) return;
    onChange(option.value);
    setIsOpen(false);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (disabled) return;

    if (!isOpen) {
      if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
        e.preventDefault();
        setIsOpen(true);
      }
      return;
    }

    if (e.key === "Escape") {
      e.preventDefault();
      setIsOpen(false);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex((prev) =>
        prev < filteredOptions.length - 1 ? prev + 1 : prev
      );
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (filteredOptions[highlightedIndex]) {
        handleSelect(filteredOptions[highlightedIndex]);
      }
    }
  }

  const isDark = variant === "dark";

  return (
    <div
      ref={containerRef}
      className={`relative inline-block text-left ${containerClassName}`}
      onKeyDown={handleKeyDown}
    >
      {/* Hidden native select for automated test frameworks and form submitters */}
      <select
        id={selectId}
        name={name}
        data-testid={dataTestId}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        required={required}
        aria-hidden="true"
        tabIndex={-1}
        className="sr-only pointer-events-none"
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} disabled={opt.disabled}>
            {opt.label} {opt.sublabel ? `· ${opt.sublabel}` : ""}
          </option>
        ))}
      </select>

      {/* Visible Trigger Button */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen(!isOpen)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        className={`w-full flex items-center justify-between gap-2 px-3 py-1.5 text-xs sm:text-sm font-medium rounded-lg border transition-all text-left focus:outline-none focus:ring-2 disabled:opacity-50 disabled:cursor-not-allowed ${
          isDark
            ? "bg-[#1e293b] border-slate-700 text-white hover:bg-slate-800 focus:ring-blue-500"
            : "bg-white border-slate-300 text-slate-800 hover:bg-slate-50 focus:ring-indigo-500 focus:border-indigo-500 shadow-2xs"
        } ${className}`}
      >
        <span className="truncate block">
          {selectedOption ? (
            <span>
              {selectedOption.label}
              {selectedOption.sublabel && (
                <span className={`ml-1.5 text-xs ${isDark ? "text-slate-400" : "text-slate-500"}`}>
                  ({selectedOption.sublabel})
                </span>
              )}
            </span>
          ) : (
            <span className={isDark ? "text-slate-500" : "text-slate-400"}>
              {placeholder}
            </span>
          )}
        </span>

        {/* Chevron icon */}
        <svg
          className={`w-4 h-4 shrink-0 transition-transform duration-200 ${
            isOpen ? "transform rotate-180" : ""
          } ${isDark ? "text-slate-400" : "text-slate-500"}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div
          className={`absolute left-0 mt-1 w-full min-w-[240px] max-w-[420px] rounded-xl border shadow-xl z-50 overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-100 ${
            isDark
              ? "bg-[#1e293b] border-slate-700 text-white shadow-black/50"
              : "bg-white border-slate-200 text-slate-800 shadow-slate-200/80"
          }`}
        >
          {/* Search Header */}
          <div
            className={`p-2 border-b flex items-center gap-2 sticky top-0 z-10 ${
              isDark ? "bg-slate-900/90 border-slate-700/80" : "bg-slate-50/95 border-slate-100"
            }`}
          >
            <svg
              className={`w-3.5 h-3.5 shrink-0 ml-1 ${isDark ? "text-slate-400" : "text-slate-400"}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setHighlightedIndex(0);
              }}
              placeholder={searchPlaceholder}
              className={`w-full bg-transparent text-xs sm:text-sm px-1 py-1 focus:outline-none ${
                isDark
                  ? "text-white placeholder-slate-500"
                  : "text-slate-800 placeholder-slate-400"
              }`}
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className={`p-1 rounded text-xs hover:opacity-75 ${
                  isDark ? "text-slate-400 hover:text-white" : "text-slate-400 hover:text-slate-600"
                }`}
              >
                ✕
              </button>
            )}
          </div>

          {/* Options List */}
          <ul
            ref={listRef}
            role="listbox"
            className="max-h-60 overflow-y-auto p-1 divide-y divide-transparent focus:outline-none"
          >
            {filteredOptions.length === 0 ? (
              <li
                className={`px-3 py-4 text-xs text-center ${
                  isDark ? "text-slate-400" : "text-slate-500"
                }`}
              >
                No options matching &ldquo;{searchQuery}&rdquo;
              </li>
            ) : (
              filteredOptions.map((opt, index) => {
                const isSelected = String(opt.value) === String(value);
                const isHighlighted = index === highlightedIndex;

                let itemClass = `flex items-center justify-between px-3 py-2 text-xs sm:text-sm rounded-lg cursor-pointer transition-colors ${
                  opt.disabled ? "opacity-40 cursor-not-allowed" : ""
                } `;

                if (isDark) {
                  if (isSelected) {
                    itemClass += "bg-blue-600/30 text-blue-300 font-semibold";
                  } else if (isHighlighted) {
                    itemClass += "bg-slate-800 text-white";
                  } else {
                    itemClass += "text-slate-300 hover:bg-slate-800/80 hover:text-white";
                  }
                } else {
                  if (isSelected) {
                    itemClass += "bg-indigo-50 text-indigo-900 font-semibold";
                  } else if (isHighlighted) {
                    itemClass += "bg-slate-100 text-slate-900";
                  } else {
                    itemClass += "text-slate-700 hover:bg-slate-50 hover:text-slate-900";
                  }
                }

                return (
                  <li
                    key={opt.value}
                    role="option"
                    aria-selected={isSelected}
                    onClick={() => handleSelect(opt)}
                    onMouseEnter={() => setHighlightedIndex(index)}
                    className={itemClass}
                  >
                    <div className="truncate pr-2">
                      <span className="block truncate">{opt.label}</span>
                      {opt.sublabel && (
                        <span
                          className={`text-[11px] block truncate ${
                            isDark ? "text-slate-400" : "text-slate-500"
                          }`}
                        >
                          {opt.sublabel}
                        </span>
                      )}
                    </div>
                    {isSelected && (
                      <svg
                        className={`w-4 h-4 shrink-0 ${isDark ? "text-blue-400" : "text-indigo-600"}`}
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2.5}
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                    )}
                  </li>
                );
              })
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
